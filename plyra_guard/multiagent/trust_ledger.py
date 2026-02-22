"""
Trust Ledger
~~~~~~~~~~~~

Agent identity and trust level registry for multi-agent systems.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from plyra_guard.core.verdict import TrustLevel
from plyra_guard.exceptions import AgentNotRegisteredError

__all__ = ["TrustLedger", "AgentProfile"]

logger = logging.getLogger(__name__)


@dataclass
class AgentProfile:
    """Profile for a registered agent."""

    agent_id: str
    trust_level: TrustLevel
    trust_score: float = 0.5
    can_delegate_to: list[str] = field(default_factory=list)
    max_actions_per_run: int = 100
    action_count: int = 0
    error_count: int = 0
    violation_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def error_rate(self) -> float:
        """Calculate the error rate for this agent."""
        if self.action_count == 0:
            return 0.0
        return self.error_count / self.action_count


class TrustLedger:
    """
    Registry of agent identities and their trust levels.

    Trust levels modify the effective risk threshold:
        effective_threshold = base_threshold * caller_trust_level

    Unknown agents are blocked by default.
    """

    def __init__(
        self,
        block_unknown: bool = True,
        default_trust_level: TrustLevel = TrustLevel.UNKNOWN,
    ) -> None:
        self._agents: dict[str, AgentProfile] = {}
        self._block_unknown = block_unknown
        self._default_trust_level = default_trust_level
        self._lock = asyncio.Lock()
        self._sync_lock = threading.RLock()  # sync-only fallback

    def register(
        self,
        agent_id: str,
        trust_level: TrustLevel,
        can_delegate_to: list[str] | None = None,
        max_actions_per_run: int = 100,
    ) -> AgentProfile:
        """
        Register an agent with a trust level.

        Args:
            agent_id: Unique agent identifier.
            trust_level: The trust classification.
            can_delegate_to: List of agent IDs this agent can delegate to.
            max_actions_per_run: Max actions allowed per run.

        Returns:
            The created AgentProfile.
        """
        profile = AgentProfile(
            agent_id=agent_id,
            trust_level=trust_level,
            trust_score=trust_level.score(),
            can_delegate_to=can_delegate_to or [],
            max_actions_per_run=max_actions_per_run,
        )
        with self._sync_lock:
            self._agents[agent_id] = profile

        logger.info(
            "Registered agent '%s' with trust level %s",
            agent_id,
            trust_level.value,
        )
        return profile

    def get(self, agent_id: str) -> AgentProfile:
        """
        Get the profile for a registered agent.

        Raises:
            AgentNotRegisteredError: If the agent is not registered and
                block_unknown is True.
        """
        with self._sync_lock:
            if agent_id in self._agents:
                return self._agents[agent_id]

        if self._block_unknown:
            raise AgentNotRegisteredError(f"Agent '{agent_id}' is not registered")

        # Return a default profile for unknown agents
        return AgentProfile(
            agent_id=agent_id,
            trust_level=self._default_trust_level,
            trust_score=self._default_trust_level.score(),
        )

    def is_registered(self, agent_id: str) -> bool:
        """Check if an agent is registered."""
        return agent_id in self._agents

    def get_trust_score(self, agent_id: str) -> float:
        """Get the numeric trust score for an agent."""
        return self.get(agent_id).trust_score

    def update_trust_score(self, agent_id: str, delta: float) -> float:
        """
        Adjust an agent's trust score, clamping to [0.0, 1.0].

        Returns the new trust score.
        """
        profile = self.get(agent_id)
        with self._sync_lock:
            profile.trust_score = max(0.0, min(1.0, profile.trust_score + delta))
        return profile.trust_score

    def record_action(self, agent_id: str, success: bool) -> None:
        """Record an action outcome for the agent."""
        profile = self.get(agent_id)
        with self._sync_lock:
            profile.action_count += 1
            if not success:
                profile.error_count += 1

    def record_violation(self, agent_id: str) -> None:
        """Record a policy violation for the agent."""
        profile = self.get(agent_id)
        with self._sync_lock:
            profile.violation_count += 1
            # Trust dips on violations
            profile.trust_score = max(0.0, profile.trust_score - 0.05)

    def can_delegate(self, from_id: str, to_id: str) -> bool:
        """Check if agent from_id is allowed to delegate to to_id."""
        profile = self.get(from_id)
        if not profile.can_delegate_to:
            return True  # No restrictions
        return to_id in profile.can_delegate_to

    def has_actions_remaining(self, agent_id: str) -> bool:
        """Check if agent has actions remaining in this run."""
        profile = self.get(agent_id)
        return profile.action_count < profile.max_actions_per_run

    def list_agents(self) -> list[AgentProfile]:
        """Return all registered agent profiles."""
        return list(self._agents.values())

    def clear(self) -> None:
        """Remove all registered agents."""
        with self._sync_lock:
            self._agents.clear()
