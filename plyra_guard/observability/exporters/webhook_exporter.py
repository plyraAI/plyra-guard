"""
Webhook Exporter
~~~~~~~~~~~~~~~~

POSTs audit entries to an arbitrary URL.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from plyra_guard.core.intent import AuditEntry

__all__ = ["WebhookExporter"]

logger = logging.getLogger(__name__)


class WebhookExporter:
    """
    Exports audit entries by POSTing them as JSON to a webhook URL.

    Useful for integrating with Slack, PagerDuty, custom dashboards, etc.
    """

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: int = 10,
    ) -> None:
        self._url = url
        self._headers = headers or {}
        self._timeout = timeout

    def export(self, entry: AuditEntry) -> None:
        """POST the audit entry as JSON to the webhook URL."""
        payload = json.dumps(entry.to_dict(), default=str).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            **self._headers,
        }

        try:
            req = urllib.request.Request(
                self._url,
                data=payload,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                if resp.status >= 400:
                    logger.warning(
                        "Webhook returned status %d for action %s",
                        resp.status,
                        entry.action_id,
                    )
        except (urllib.error.URLError, OSError) as exc:
            logger.error("Webhook export failed: %s", exc)
