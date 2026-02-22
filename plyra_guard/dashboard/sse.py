"""
Dashboard SSE
~~~~~~~~~~~~~

Server-Sent Events generator for the live action feed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from plyra_guard.observability.audit_log import AuditLog

__all__ = ["sse_event_generator", "format_sse_event"]

logger = logging.getLogger(__name__)


def format_sse_event(entry_dict: dict[str, Any]) -> str:
    """Format an AuditEntry dict as an SSE event string.

    Returns a string like::

        event: action
        id: <action_id>
        data: {json payload}

    """
    action_id = entry_dict.get("action_id", "")
    payload = json.dumps(entry_dict, default=str)
    return f"event: action\nid: {action_id}\ndata: {payload}\n\n"


async def sse_event_generator(
    audit_log: AuditLog,
    *,
    poll_interval: float = 1.0,
    keepalive_interval: float = 15.0,
) -> AsyncGenerator[dict[str, str], None]:
    """Yield SSE-compatible dicts for ``sse-starlette``.

    Polls the audit log for new entries.  Sends a keepalive
    comment every *keepalive_interval* seconds when idle.

    Each yielded dict has keys ``event``, ``id``, ``data``.
    """
    seen: set[str] = set()
    # seed with existing entries
    for entry in audit_log.query():
        seen.add(entry.action_id)

    since_keepalive = 0.0

    while True:
        emitted = False
        for entry in audit_log.query():
            if entry.action_id not in seen:
                seen.add(entry.action_id)
                yield {
                    "event": "action",
                    "id": entry.action_id,
                    "data": json.dumps(entry.to_dict(), default=str),
                }
                emitted = True

        if not emitted:
            since_keepalive += poll_interval
            if since_keepalive >= keepalive_interval:
                yield {"comment": "ping"}
                since_keepalive = 0.0

        await asyncio.sleep(poll_interval)
