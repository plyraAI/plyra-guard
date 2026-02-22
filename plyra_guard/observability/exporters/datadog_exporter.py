"""
Datadog Exporter
~~~~~~~~~~~~~~~~

Exports audit entries to Datadog via ddtrace.
"""

from __future__ import annotations

import logging
from typing import Any

from plyra_guard.core.intent import AuditEntry

__all__ = ["DatadogExporter"]

logger = logging.getLogger(__name__)


class DatadogExporter:
    """
    Exports audit entries to Datadog.

    Requires the `ddtrace` package (install with
    ``pip install plyra_guard[datadog]``).
    """

    def __init__(self, service_name: str = "plyra_guard") -> None:
        self._service_name = service_name
        self._tracer: Any = None
        self._setup()

    def _setup(self) -> None:
        """Initialize the Datadog tracer."""
        try:
            from ddtrace import tracer

            self._tracer = tracer
        except ImportError:
            logger.warning(
                "ddtrace not installed. Install with: pip install plyra_guard[datadog]"
            )

    def export(self, entry: AuditEntry) -> None:
        """Export an audit entry as a Datadog span."""
        if self._tracer is None:
            return

        with self._tracer.trace(
            "plyra_guard.action",
            service=self._service_name,
        ) as span:
            span.set_tag("action_id", entry.action_id)
            span.set_tag("agent_id", entry.agent_id)
            span.set_tag("action_type", entry.action_type)
            span.set_tag("verdict", entry.verdict.value)
            span.set_tag("risk_score", entry.risk_score)
            span.set_tag("duration_ms", entry.duration_ms)
            if entry.policy_triggered:
                span.set_tag("policy_triggered", entry.policy_triggered)
            if entry.error:
                span.error = 1
                span.set_tag("error.msg", entry.error)
