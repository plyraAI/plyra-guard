"""
Rate Limiter Evaluator
~~~~~~~~~~~~~~~~~~~~~~

Enforces per-agent and per-tool rate limits using a sliding-window approach.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict
from dataclasses import dataclass

from plyra_guard.core.intent import ActionIntent, EvaluatorResult
from plyra_guard.core.verdict import Verdict
from plyra_guard.evaluators.base import BaseEvaluator

__all__ = ["RateLimiter", "RateLimit"]


@dataclass
class RateLimit:
    """A rate limit specification."""

    max_calls: int
    period_seconds: int

    @classmethod
    def from_string(cls, spec: str) -> RateLimit:
        """
        Parse a rate limit string like '60/min', '5/sec', '100/hour'.

        Args:
            spec: Rate limit string in format 'N/period'.

        Returns:
            A RateLimit instance.
        """
        parts = spec.strip().split("/")
        if len(parts) != 2:
            raise ValueError(f"Invalid rate limit spec: {spec!r}")

        max_calls = int(parts[0])
        period = parts[1].strip().lower()

        period_map = {
            "sec": 1,
            "second": 1,
            "s": 1,
            "min": 60,
            "minute": 60,
            "m": 60,
            "hour": 3600,
            "hr": 3600,
            "h": 3600,
            "day": 86400,
            "d": 86400,
        }

        period_seconds = period_map.get(period)
        if period_seconds is None:
            raise ValueError(f"Unknown period: {period!r}")

        return cls(max_calls=max_calls, period_seconds=period_seconds)


class _SlidingWindow:
    """Thread-safe sliding window counter."""

    def __init__(self) -> None:
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()
        self._sync_lock = threading.RLock()  # sync-only fallback

    def add(self, ts: float | None = None) -> None:
        """Record a new event."""
        with self._sync_lock:
            self._timestamps.append(ts or time.monotonic())

    def count_in_window(self, window_seconds: int) -> int:
        """Count events in the last window_seconds."""
        cutoff = time.monotonic() - window_seconds
        with self._sync_lock:
            # Prune old entries
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            return len(self._timestamps)

    async def add_async(self, ts: float | None = None) -> None:
        """Async version of add."""
        async with self._lock:
            self._timestamps.append(ts or time.monotonic())

    async def count_in_window_async(self, window_seconds: int) -> int:
        """Async version of count_in_window."""
        cutoff = time.monotonic() - window_seconds
        async with self._lock:
            self._timestamps = [t for t in self._timestamps if t > cutoff]
            return len(self._timestamps)


class RateLimiter(BaseEvaluator):
    """
    Enforces per-agent and per-tool rate limits.

    Limits can be set globally (default), per-tool, or per-agent.
    Uses a sliding window approach for accurate rate limiting.
    """

    def __init__(
        self,
        default_limit: str = "60/min",
        per_tool_limits: dict[str, str] | None = None,
        per_agent_limits: dict[str, str] | None = None,
    ) -> None:
        self._default_limit = RateLimit.from_string(default_limit)
        self._per_tool_limits: dict[str, RateLimit] = {}
        self._per_agent_limits: dict[str, RateLimit] = {}

        if per_tool_limits:
            for tool, spec in per_tool_limits.items():
                self._per_tool_limits[tool] = RateLimit.from_string(spec)

        if per_agent_limits:
            for agent, spec in per_agent_limits.items():
                self._per_agent_limits[agent] = RateLimit.from_string(spec)

        # Sliding windows: keyed by (agent_id, tool_name)
        self._windows: dict[tuple[str, str], _SlidingWindow] = defaultdict(
            _SlidingWindow
        )
        # Global agent windows
        self._agent_windows: dict[str, _SlidingWindow] = defaultdict(_SlidingWindow)

    @property
    def name(self) -> str:
        return "rate_limiter"

    @property
    def priority(self) -> int:
        return 40

    def _get_limit_for_tool(self, tool_name: str) -> RateLimit:
        """Get the applicable rate limit for a tool."""
        # Check exact match first, then prefix match
        if tool_name in self._per_tool_limits:
            return self._per_tool_limits[tool_name]
        for pattern, limit in self._per_tool_limits.items():
            if tool_name.startswith(pattern.rstrip("*")):
                return limit
        return self._default_limit

    def _get_limit_for_agent(self, agent_id: str) -> RateLimit:
        """Get the applicable rate limit for an agent."""
        return self._per_agent_limits.get(agent_id, self._default_limit)

    def record_action(self, agent_id: str, tool_name: str) -> None:
        """Record an action for rate limiting purposes."""
        key = (agent_id, tool_name)
        self._windows[key].add()
        self._agent_windows[agent_id].add()

    async def record_call(self, tool_name: str, agent_id: str) -> None:
        """Async: record a call for rate limiting."""
        key = (agent_id, tool_name)
        await self._windows[key].add_async()
        await self._agent_windows[agent_id].add_async()

    async def get_call_count(self, tool_name: str, window_seconds: int = 60) -> int:
        """Async: get the call count for a tool across all agents."""
        total = 0
        for (_, tname), window in self._windows.items():
            if tname == tool_name:
                total += await window.count_in_window_async(window_seconds)
        return total

    def evaluate(self, intent: ActionIntent) -> EvaluatorResult:
        """Check if the action would exceed rate limits."""
        agent_id = intent.agent_id
        tool_name = intent.action_type

        # Check per-tool limit
        tool_limit = self._get_limit_for_tool(tool_name)
        key = (agent_id, tool_name)
        tool_count = self._windows[key].count_in_window(tool_limit.period_seconds)

        if tool_count >= tool_limit.max_calls:
            return EvaluatorResult(
                verdict=Verdict.BLOCK,
                reason=(
                    f"Rate limit exceeded for {tool_name}: "
                    f"{tool_count}/{tool_limit.max_calls} in "
                    f"{tool_limit.period_seconds}s"
                ),
                confidence=1.0,
                evaluator_name=self.name,
                metadata={
                    "tool_name": tool_name,
                    "current_count": tool_count,
                    "limit": tool_limit.max_calls,
                    "period_seconds": tool_limit.period_seconds,
                },
            )

        # Check per-agent limit
        agent_limit = self._get_limit_for_agent(agent_id)
        agent_count = self._agent_windows[agent_id].count_in_window(
            agent_limit.period_seconds
        )

        if agent_count >= agent_limit.max_calls:
            return EvaluatorResult(
                verdict=Verdict.BLOCK,
                reason=(
                    f"Agent rate limit exceeded for {agent_id}: "
                    f"{agent_count}/{agent_limit.max_calls} in "
                    f"{agent_limit.period_seconds}s"
                ),
                confidence=1.0,
                evaluator_name=self.name,
                metadata={
                    "agent_id": agent_id,
                    "current_count": agent_count,
                    "limit": agent_limit.max_calls,
                    "period_seconds": agent_limit.period_seconds,
                },
            )

        # Record this action
        self.record_action(agent_id, tool_name)

        return EvaluatorResult(
            verdict=Verdict.ALLOW,
            reason="Rate limits OK",
            confidence=1.0,
            evaluator_name=self.name,
        )
