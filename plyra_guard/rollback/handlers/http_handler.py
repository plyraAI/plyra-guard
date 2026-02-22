"""
HTTP Rollback Handler
~~~~~~~~~~~~~~~~~~~~~

Handles rollback for HTTP operations by calling a compensation endpoint.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from plyra_guard.core.intent import ActionIntent
from plyra_guard.rollback.handlers.base_handler import BaseRollbackHandler, Snapshot

__all__ = ["HttpRollbackHandler"]

logger = logging.getLogger(__name__)


class HttpRollbackHandler(BaseRollbackHandler):
    """
    Rollback handler for HTTP operations.

    Calls a registered compensation URL to undo HTTP POST/PUT/PATCH operations.
    The compensation URL is extracted from the action's metadata or parameters.
    """

    def __init__(self, timeout: int = 30) -> None:
        self._timeout = timeout

    @property
    def action_types(self) -> list[str]:
        return ["http.post", "http.put", "http.patch"]

    def capture(self, intent: ActionIntent) -> Snapshot:
        """Capture HTTP request details."""
        state: dict[str, Any] = {
            "url": intent.parameters.get("url", ""),
            "method": intent.action_type.split(".")[-1].upper(),
            "compensation_url": (
                intent.metadata.get("compensation_url")
                or intent.parameters.get("compensation_url", "")
            ),
            "request_body": intent.parameters.get("body", {}),
        }

        return Snapshot(
            action_id=intent.action_id,
            action_type=intent.action_type,
            state=state,
        )

    def restore(self, snapshot: Snapshot) -> bool:
        """Call the compensation URL to undo the HTTP action."""
        compensation_url = snapshot.state.get("compensation_url", "")

        if not compensation_url:
            logger.warning(
                "No compensation_url for action %s — cannot rollback",
                snapshot.action_id,
            )
            return False

        payload = json.dumps(
            {
                "action_id": snapshot.action_id,
                "original_url": snapshot.state.get("url", ""),
                "original_method": snapshot.state.get("method", ""),
                "original_body": snapshot.state.get("request_body", {}),
            }
        ).encode("utf-8")

        try:
            req = urllib.request.Request(
                compensation_url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                if resp.status < 300:
                    logger.info(
                        "HTTP rollback succeeded for action %s",
                        snapshot.action_id,
                    )
                    return True
                logger.warning(
                    "HTTP rollback returned status %d for action %s",
                    resp.status,
                    snapshot.action_id,
                )
                return False
        except (urllib.error.URLError, OSError) as exc:
            logger.error(
                "HTTP rollback failed for action %s: %s",
                snapshot.action_id,
                exc,
            )
            return False
