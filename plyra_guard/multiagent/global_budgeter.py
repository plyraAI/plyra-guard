"""
Global Budget Manager
~~~~~~~~~~~~~~~~~~~~~

Cross-agent cost aggregation and enforcement for multi-agent systems.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict

from plyra_guard.core.intent import ActionIntent, EvaluatorResult
from plyra_guard.core.verdict import Verdict

__all__ = ["GlobalBudgetManager"]

logger = logging.getLogger(__name__)


class GlobalBudgetManager:
    """
    Tracks cumulative cost per task across ALL agents.

    Detects:
    - Individual agents exceeding per-agent-per-run budgets
    - Tasks exceeding per-task budgets
    - Budget gaming: many cheap sub-agents collectively exceeding task budget
    """

    def __init__(
        self,
        per_task_budget: float = 5.00,
        per_agent_per_run: float = 1.00,
        currency: str = "USD",
    ) -> None:
        self._per_task_budget = per_task_budget
        self._per_agent_per_run = per_agent_per_run
        self._currency = currency

        self._task_spend: dict[str, float] = defaultdict(float)
        self._agent_spend: dict[str, float] = defaultdict(float)
        self._task_agents: dict[str, set[str]] = defaultdict(set)
        self._action_costs: dict[
            str, tuple[str, str, float]
        ] = {}  # action_id -> (task_id, agent_id, cost)
        self._lock = asyncio.Lock()
        self._sync_lock = threading.RLock()  # sync-only fallback

    def check(self, intent: ActionIntent) -> EvaluatorResult | None:
        """
        Check if the action would exceed budget limits.

        Returns None if within budget, or an EvaluatorResult with
        BLOCK/ESCALATE verdict.
        """
        cost = intent.estimated_cost
        agent_id = intent.agent_id
        task_id = intent.task_id

        with self._sync_lock:
            # Check per-agent budget
            agent_projected = self._agent_spend[agent_id] + cost
            if agent_projected > self._per_agent_per_run:
                return EvaluatorResult(
                    verdict=Verdict.BLOCK,
                    reason=(
                        f"Agent '{agent_id}' budget exceeded: "
                        f"{self._currency} {agent_projected:.2f} > "
                        f"{self._currency} {self._per_agent_per_run:.2f}"
                    ),
                    confidence=1.0,
                    evaluator_name="global_budgeter",
                )

            # Check per-task budget
            if task_id:
                task_projected = self._task_spend[task_id] + cost
                if task_projected > self._per_task_budget:
                    return EvaluatorResult(
                        verdict=Verdict.BLOCK,
                        reason=(
                            f"Task '{task_id}' budget exceeded: "
                            f"{self._currency} {task_projected:.2f} > "
                            f"{self._currency} {self._per_task_budget:.2f}"
                        ),
                        confidence=1.0,
                        evaluator_name="global_budgeter",
                    )

                # Check for budget gaming (many agents, small amounts)
                num_agents = len(self._task_agents.get(task_id, set()))
                if num_agents > 3 and task_projected > self._per_task_budget * 0.8:
                    return EvaluatorResult(
                        verdict=Verdict.ESCALATE,
                        reason=(
                            f"Potential budget gaming: {num_agents} agents "
                            f"on task '{task_id}' approaching budget limit "
                            f"({self._currency} {task_projected:.2f})"
                        ),
                        confidence=0.8,
                        evaluator_name="global_budgeter",
                    )

        return None

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
                self._task_agents[task_id].add(agent_id)

    def get_task_spend(self, task_id: str) -> float:
        """Get total spend for a task across all agents."""
        return self._task_spend.get(task_id, 0.0)

    def get_agent_spend(self, agent_id: str) -> float:
        """Get total spend for an agent in the current run."""
        return self._agent_spend.get(agent_id, 0.0)

    def get_task_agent_count(self, task_id: str) -> int:
        """Get the number of agents that have spent on a task."""
        return len(self._task_agents.get(task_id, set()))

    def reset(self) -> None:
        """Reset all budget tracking."""
        with self._sync_lock:
            self._task_spend.clear()
            self._agent_spend.clear()
            self._task_agents.clear()
            self._action_costs.clear()

    # ── Async versions ────────────────────────────────────────────

    async def add_spend(
        self,
        task_id: str,
        agent_id: str,
        cost: float,
    ) -> None:
        """Async version of record_cost."""
        async with self._lock:
            self._agent_spend[agent_id] += cost
            self._task_spend[task_id] += cost
            self._task_agents[task_id].add(agent_id)

    async def get_task_total(self, task_id: str) -> float:
        """Async version of get_task_spend."""
        async with self._lock:
            return self._task_spend.get(task_id, 0.0)

    async def check_budget(self, intent: ActionIntent) -> EvaluatorResult | None:
        """Async version of check."""
        cost = intent.estimated_cost
        agent_id = intent.agent_id
        task_id = intent.task_id

        async with self._lock:
            agent_projected = self._agent_spend[agent_id] + cost
            if agent_projected > self._per_agent_per_run:
                return EvaluatorResult(
                    verdict=Verdict.BLOCK,
                    reason=(
                        f"Agent '{agent_id}' budget exceeded: "
                        f"{self._currency} {agent_projected:.2f} > "
                        f"{self._currency} {self._per_agent_per_run:.2f}"
                    ),
                    confidence=1.0,
                    evaluator_name="global_budgeter",
                )

            if task_id:
                task_projected = self._task_spend[task_id] + cost
                if task_projected > self._per_task_budget:
                    return EvaluatorResult(
                        verdict=Verdict.BLOCK,
                        reason=(
                            f"Task '{task_id}' budget exceeded: "
                            f"{self._currency} {task_projected:.2f} > "
                            f"{self._currency} {self._per_task_budget:.2f}"
                        ),
                        confidence=1.0,
                        evaluator_name="global_budgeter",
                    )

        return None

    # ── Action registration & recrediting (FIX 3) ────────────────

    def register_action(
        self,
        task_id: str,
        agent_id: str,
        action_id: str,
        cost: float,
    ) -> None:
        """
        Register an action's cost for tracking.
        Called when an action is approved and executed.
        Enables budget recrediting on rollback.
        """
        with self._sync_lock:
            self._action_costs[action_id] = (task_id, agent_id, cost)

    async def register_action_async(
        self,
        task_id: str,
        agent_id: str,
        action_id: str,
        cost: float,
    ) -> None:
        """Async version of register_action."""
        async with self._lock:
            self._action_costs[action_id] = (task_id, agent_id, cost)

    def recredit(
        self,
        task_id: str,
        agent_id: str,
        action_id: str,
    ) -> float:
        """
        Recredits the budget for a rolled-back action.
        Returns the amount recredited.
        Called by RollbackCoordinator after successful rollback.
        """
        with self._sync_lock:
            record = self._action_costs.pop(action_id, None)
            if record is None:
                return 0.0
            _, _, cost = record
            self._agent_spend[agent_id] = max(0.0, self._agent_spend[agent_id] - cost)
            self._task_spend[task_id] = max(0.0, self._task_spend[task_id] - cost)
            logger.info(
                "Recredited %s %.2f for action %s (agent=%s, task=%s)",
                self._currency,
                cost,
                action_id,
                agent_id,
                task_id,
            )
            return cost
