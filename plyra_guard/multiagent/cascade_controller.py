"""
Cascade Controller
~~~~~~~~~~~~~~~~~~

Enforces delegation depth limits, concurrent delegation limits,
and cycle detection in multi-agent systems.
"""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict

from plyra_guard.core.intent import ActionIntent, EvaluatorResult
from plyra_guard.core.verdict import Verdict

__all__ = ["CascadeController"]


class CascadeController:
    """
    Enforces cascade safety limits:

    1. max_delegation_depth: Maximum hops in the instruction chain.
    2. max_concurrent_delegations: Maximum parallel active actions per orchestrator.
    3. cycle_detection: Blocks if an agent appears twice in the chain.
    """

    def __init__(
        self,
        max_delegation_depth: int = 4,
        max_concurrent_delegations: int = 10,
    ) -> None:
        self._max_depth = max_delegation_depth
        self._max_concurrent = max_concurrent_delegations
        self._active_delegations: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()
        self._sync_lock = threading.RLock()  # sync-only fallback

    def check(self, intent: ActionIntent) -> EvaluatorResult | None:
        """
        Check cascade safety limits for an intent.

        Returns:
            None if all checks pass, or an EvaluatorResult with a BLOCK verdict.
        """
        chain = intent.instruction_chain

        # 1. Check delegation depth
        if len(chain) > self._max_depth:
            return EvaluatorResult(
                verdict=Verdict.BLOCK,
                reason=(
                    f"Delegation depth {len(chain)} exceeds maximum {self._max_depth}"
                ),
                confidence=1.0,
                evaluator_name="cascade_controller",
                metadata={
                    "depth": len(chain),
                    "max_depth": self._max_depth,
                },
            )

        # 2. Check for cycles
        agent_ids = [ac.agent_id for ac in chain]
        if intent.agent_id in agent_ids:
            # Current agent already appeared in the chain
            return EvaluatorResult(
                verdict=Verdict.BLOCK,
                reason=(
                    f"Cycle detected: agent '{intent.agent_id}' "
                    f"appears multiple times in delegation chain"
                ),
                confidence=1.0,
                evaluator_name="cascade_controller",
                metadata={
                    "agent_id": intent.agent_id,
                    "chain": agent_ids,
                },
            )

        # Check for duplicate agents within the chain
        if len(agent_ids) != len(set(agent_ids)):
            duplicates = [aid for aid in set(agent_ids) if agent_ids.count(aid) > 1]
            return EvaluatorResult(
                verdict=Verdict.BLOCK,
                reason=(
                    f"Cycle detected: agents {duplicates} appear "
                    f"multiple times in delegation chain"
                ),
                confidence=1.0,
                evaluator_name="cascade_controller",
                metadata={"duplicates": duplicates},
            )

        # 3. Check concurrent delegations
        if chain:
            orchestrator_id = chain[0].agent_id
            with self._sync_lock:
                active = self._active_delegations[orchestrator_id]
            if active >= self._max_concurrent:
                return EvaluatorResult(
                    verdict=Verdict.BLOCK,
                    reason=(
                        f"Orchestrator '{orchestrator_id}' has "
                        f"{active} concurrent delegations "
                        f"(max: {self._max_concurrent})"
                    ),
                    confidence=1.0,
                    evaluator_name="cascade_controller",
                    metadata={
                        "orchestrator_id": orchestrator_id,
                        "active": active,
                        "max": self._max_concurrent,
                    },
                )

        return None

    def record_delegation_start(self, orchestrator_id: str) -> None:
        """Record the start of a delegated action."""
        with self._sync_lock:
            self._active_delegations[orchestrator_id] += 1

    def record_delegation_end(self, orchestrator_id: str) -> None:
        """Record the end of a delegated action."""
        with self._sync_lock:
            if self._active_delegations[orchestrator_id] > 0:
                self._active_delegations[orchestrator_id] -= 1

    def get_active_count(self, orchestrator_id: str) -> int:
        """Get the number of active delegations for an orchestrator."""
        return self._active_delegations.get(orchestrator_id, 0)

    def reset(self) -> None:
        """Reset all delegation counters."""
        with self._sync_lock:
            self._active_delegations.clear()
