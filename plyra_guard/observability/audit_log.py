"""
Audit Log
~~~~~~~~~

Structured audit log writer that records all evaluated actions.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from plyra_guard.core.intent import AuditEntry, AuditFilter, GuardMetrics
from plyra_guard.core.verdict import Verdict

__all__ = ["AuditLog"]

logger = logging.getLogger(__name__)


class AuditLog:
    """
    In-memory structured audit log with filtering and export support.

    Every action evaluated by ActionGuard gets an entry here,
    regardless of verdict. Entries are forwarded to configured exporters.
    """

    def __init__(self, max_entries: int = 10000) -> None:
        self._entries: list[AuditEntry] = []
        self._max_entries = max_entries
        self._lock = asyncio.Lock()
        self._sync_lock = threading.RLock()  # sync-only fallback
        self._exporters: list[Any] = []

    def add_exporter(self, exporter: Any) -> None:
        """Add an exporter to receive audit entries."""
        self._exporters.append(exporter)

    def write(self, entry: AuditEntry) -> None:
        """
        Write an entry to the audit log and forward to exporters.

        Args:
            entry: The audit entry to record.
        """
        with self._sync_lock:
            self._entries.append(entry)
            # Evict oldest if over limit
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries :]

        # Forward to exporters
        for exporter in self._exporters:
            try:
                exporter.export(entry)
            except Exception as exc:
                logger.error(
                    "Exporter %s failed: %s",
                    type(exporter).__name__,
                    exc,
                )

    async def append_async(self, entry: AuditEntry) -> None:
        """Async version of write."""
        async with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max_entries:
                self._entries = self._entries[-self._max_entries :]

        # Forward to exporters
        for exporter in self._exporters:
            try:
                exporter.export(entry)
            except Exception as exc:
                logger.error(
                    "Exporter %s failed: %s",
                    type(exporter).__name__,
                    exc,
                )

    def query(self, filters: AuditFilter | None = None) -> list[AuditEntry]:
        """
        Query the audit log with optional filters.

        Args:
            filters: Optional filter criteria.

        Returns:
            Matching audit entries.
        """
        if filters is None:
            with self._sync_lock:
                return list(self._entries)

        results: list[AuditEntry] = []
        with self._sync_lock:
            for entry in self._entries:
                if filters.agent_id and entry.agent_id != filters.agent_id:
                    continue
                if filters.task_id and entry.task_id != filters.task_id:
                    continue
                if filters.verdict and entry.verdict != filters.verdict:
                    continue
                if filters.action_type and entry.action_type != filters.action_type:
                    continue
                if filters.from_time and entry.timestamp < filters.from_time:
                    continue
                if filters.to_time and entry.timestamp > filters.to_time:
                    continue
                results.append(entry)

                if len(results) >= filters.limit:
                    break

        return results

    def get_metrics(self) -> GuardMetrics:
        """Compute aggregate metrics from the audit log."""
        metrics = GuardMetrics()

        with self._sync_lock:
            entries = list(self._entries)

        if not entries:
            return metrics

        metrics.total_actions = len(entries)
        total_risk = 0.0
        total_duration = 0

        for entry in entries:
            total_risk += entry.risk_score
            total_duration += entry.duration_ms

            if entry.verdict == Verdict.ALLOW:
                metrics.allowed_actions += 1
            elif entry.verdict == Verdict.BLOCK:
                metrics.blocked_actions += 1
            elif entry.verdict == Verdict.ESCALATE:
                metrics.escalated_actions += 1
            elif entry.verdict == Verdict.WARN:
                metrics.warned_actions += 1
            elif entry.verdict == Verdict.DEFER:
                metrics.deferred_actions += 1

            if entry.rolled_back:
                metrics.rollbacks += 1

            # Per-agent
            metrics.actions_by_agent[entry.agent_id] = (
                metrics.actions_by_agent.get(entry.agent_id, 0) + 1
            )
            # Per-type
            metrics.actions_by_type[entry.action_type] = (
                metrics.actions_by_type.get(entry.action_type, 0) + 1
            )
            # Per-policy
            if entry.policy_triggered:
                metrics.verdicts_by_policy[entry.policy_triggered] = (
                    metrics.verdicts_by_policy.get(entry.policy_triggered, 0) + 1
                )

        metrics.avg_risk_score = total_risk / len(entries)
        metrics.avg_duration_ms = total_duration / len(entries)

        return metrics

    def clear(self) -> None:
        """Clear all audit entries."""
        with self._sync_lock:
            self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
