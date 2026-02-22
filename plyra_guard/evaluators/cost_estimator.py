"""
Cost Estimator Evaluator
~~~~~~~~~~~~~~~~~~~~~~~~

Estimates and enforces budget limits for actions based on projected
token and API costs.
"""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict

from plyra_guard.core.intent import ActionIntent, EvaluatorResult
from plyra_guard.core.verdict import Verdict
from plyra_guard.evaluators.base import BaseEvaluator

__all__ = ["CostEstimator"]


class CostEstimator(BaseEvaluator):
    """
    Estimates action costs and enforces budget thresholds.

    Tracks cumulative spend per-task and per-agent, blocking or escalating
    when projected costs would exceed configured limits.
    """

    def __init__(
        self,
        per_task_budget: float = 5.00,
        per_agent_budget: float = 1.00,
        escalate_threshold: float = 0.50,
        currency: str = "USD",
    ) -> None:
        self._per_task_budget = per_task_budget
        self._per_agent_budget = per_agent_budget
        self._escalate_threshold = escalate_threshold
        self._currency = currency
        self._task_spend: dict[str, float] = defaultdict(float)
        self._agent_spend: dict[str, float] = defaultdict(float)
        self._lock = asyncio.Lock()
        self._sync_lock = threading.RLock()  # sync-only fallback

    @property
    def name(self) -> str:
        return "cost_estimator"

    @property
    def priority(self) -> int:
        return 50

    def record_cost(
        self,
        agent_id: str,
        task_id: str | None,
        cost: float,
    ) -> None:
        """Record a cost after action execution."""
        with self._sync_lock:
            self._agent_spend[agent_id] += cost
            if task_id:
                self._task_spend[task_id] += cost

    def get_agent_spend(self, agent_id: str) -> float:
        """Get total spend for an agent in the current run."""
        return self._agent_spend.get(agent_id, 0.0)

    def get_task_spend(self, task_id: str) -> float:
        """Get total spend for a task."""
        return self._task_spend.get(task_id, 0.0)

    def reset(self) -> None:
        """Reset all spend tracking."""
        with self._sync_lock:
            self._task_spend.clear()
            self._agent_spend.clear()

    def evaluate(self, intent: ActionIntent) -> EvaluatorResult:
        """Check if the action would exceed budget limits."""
        cost = intent.estimated_cost

        # Check per-agent budget
        agent_id = intent.agent_id
        with self._sync_lock:
            agent_projected = self._agent_spend[agent_id] + cost

        if agent_projected > self._per_agent_budget:
            return EvaluatorResult(
                verdict=Verdict.BLOCK,
                reason=(
                    f"Agent '{agent_id}' budget exceeded: "
                    f"projected {self._currency} {agent_projected:.2f} "
                    f"> limit {self._currency} {self._per_agent_budget:.2f}"
                ),
                confidence=1.0,
                evaluator_name=self.name,
                metadata={
                    "agent_id": agent_id,
                    "projected_spend": agent_projected,
                    "budget_limit": self._per_agent_budget,
                },
            )

        # Check per-task budget
        if intent.task_id:
            with self._sync_lock:
                task_projected = self._task_spend[intent.task_id] + cost

            if task_projected > self._per_task_budget:
                return EvaluatorResult(
                    verdict=Verdict.BLOCK,
                    reason=(
                        f"Task '{intent.task_id}' budget exceeded: "
                        f"projected {self._currency} {task_projected:.2f} "
                        f"> limit {self._currency} "
                        f"{self._per_task_budget:.2f}"
                    ),
                    confidence=1.0,
                    evaluator_name=self.name,
                    metadata={
                        "task_id": intent.task_id,
                        "projected_spend": task_projected,
                        "budget_limit": self._per_task_budget,
                    },
                )

        # Check escalation threshold for single action
        if cost > self._escalate_threshold:
            return EvaluatorResult(
                verdict=Verdict.ESCALATE,
                reason=(
                    f"Action cost {self._currency} {cost:.2f} exceeds "
                    f"escalation threshold {self._currency} "
                    f"{self._escalate_threshold:.2f}"
                ),
                confidence=0.95,
                evaluator_name=self.name,
                suggested_action="Requires human approval for high-cost action",
                metadata={
                    "estimated_cost": cost,
                    "escalation_threshold": self._escalate_threshold,
                },
            )

        return EvaluatorResult(
            verdict=Verdict.ALLOW,
            reason=f"Cost {self._currency} {cost:.2f} within budget",
            confidence=1.0,
            evaluator_name=self.name,
        )
