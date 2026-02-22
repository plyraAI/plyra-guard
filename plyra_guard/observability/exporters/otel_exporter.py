"""
OpenTelemetry Exporter
~~~~~~~~~~~~~~~~~~~~~~

Exports audit entries as OpenTelemetry spans.
"""

from __future__ import annotations

import logging
from typing import Any

from plyra_guard.core.intent import AuditEntry

try:
    from opentelemetry import trace as _otel_trace
except ImportError:
    _otel_trace = None  # type: ignore[assignment]

__all__ = ["OTelExporter"]

logger = logging.getLogger(__name__)


class OTelExporter:
    """
    Exports audit entries as OpenTelemetry spans.

    Requires the `opentelemetry-sdk` package (install with
    ``pip install plyra_guard[otel]``).
    """

    def __init__(self, service_name: str = "plyra_guard") -> None:
        self._service_name = service_name
        self._tracer: Any = None
        self._setup()

    def _setup(self) -> None:
        """Initialize the OpenTelemetry tracer."""
        if _otel_trace is None:
            logger.warning(
                "opentelemetry-sdk not installed. "
                "Install with: pip install plyra_guard[otel]"
            )
            return

        try:
            from opentelemetry.sdk.trace import TracerProvider

            provider = TracerProvider()
            _otel_trace.set_tracer_provider(provider)
            self._tracer = _otel_trace.get_tracer(self._service_name)
        except ImportError:
            logger.warning(
                "opentelemetry-sdk not installed. "
                "Install with: pip install plyra_guard[otel]"
            )
            self._tracer = None

    def export(self, entry: AuditEntry) -> None:
        """Export an audit entry as an OTel span."""
        if self._tracer is None:
            return

        with self._tracer.start_as_current_span(
            f"plyra_guard.{entry.action_type}"
        ) as span:
            span.set_attribute("action_id", entry.action_id)
            span.set_attribute("agent_id", entry.agent_id)
            span.set_attribute("action_type", entry.action_type)
            span.set_attribute("verdict", entry.verdict.value)
            span.set_attribute("risk_score", entry.risk_score)
            span.set_attribute("duration_ms", entry.duration_ms)
            if entry.policy_triggered:
                span.set_attribute("policy_triggered", entry.policy_triggered)
            if entry.error:
                span.set_attribute("error", entry.error)
                if _otel_trace is not None:
                    span.set_status(
                        _otel_trace.StatusCode.ERROR,
                        entry.error,
                    )
