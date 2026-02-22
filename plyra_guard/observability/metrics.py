"""
Metrics
~~~~~~~

Prometheus-style metrics tracking for ActionGuard.
"""

from __future__ import annotations

import asyncio
import threading

from plyra_guard.core.intent import GuardMetrics

__all__ = ["MetricsCollector"]


class MetricsCollector:
    """
    Collects and exposes Prometheus-style metrics.

    Thread-safe counter and gauge tracking for all ActionGuard operations.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = {
            "total_actions": 0,
            "allowed_actions": 0,
            "blocked_actions": 0,
            "escalated_actions": 0,
            "warned_actions": 0,
            "deferred_actions": 0,
            "rollbacks": 0,
            "rollback_failures": 0,
        }
        self._gauges: dict[str, float] = {
            "total_cost": 0.0,
            "avg_risk_score": 0.0,
            "avg_duration_ms": 0.0,
        }
        self._risk_sum: float = 0.0
        self._duration_sum: float = 0.0
        self._lock = asyncio.Lock()
        self._sync_lock = threading.RLock()  # sync-only fallback

    def increment(self, name: str, amount: int = 1) -> None:
        """Increment a counter."""
        with self._sync_lock:
            if name in self._counters:
                self._counters[name] += amount

    def add_cost(self, cost: float) -> None:
        """Add to the total cost gauge."""
        with self._sync_lock:
            self._gauges["total_cost"] += cost

    def record_risk(self, score: float) -> None:
        """Record a risk score for averaging."""
        with self._sync_lock:
            self._risk_sum += score
            total = self._counters.get("total_actions", 1)
            self._gauges["avg_risk_score"] = self._risk_sum / max(total, 1)

    def record_duration(self, ms: int) -> None:
        """Record an action duration for averaging."""
        with self._sync_lock:
            self._duration_sum += ms
            total = self._counters.get("total_actions", 1)
            self._gauges["avg_duration_ms"] = self._duration_sum / max(total, 1)

    def to_guard_metrics(self) -> GuardMetrics:
        """Export as a GuardMetrics dataclass."""
        with self._sync_lock:
            return GuardMetrics(
                total_actions=self._counters["total_actions"],
                allowed_actions=self._counters["allowed_actions"],
                blocked_actions=self._counters["blocked_actions"],
                escalated_actions=self._counters["escalated_actions"],
                warned_actions=self._counters["warned_actions"],
                deferred_actions=self._counters["deferred_actions"],
                rollbacks=self._counters["rollbacks"],
                rollback_failures=self._counters["rollback_failures"],
                total_cost=self._gauges["total_cost"],
                avg_risk_score=self._gauges["avg_risk_score"],
                avg_duration_ms=self._gauges["avg_duration_ms"],
            )

    def reset(self) -> None:
        """Reset all metrics."""
        with self._sync_lock:
            for key in self._counters:
                self._counters[key] = 0
            for key in self._gauges:
                self._gauges[key] = 0.0
            self._risk_sum = 0.0
            self._duration_sum = 0.0
