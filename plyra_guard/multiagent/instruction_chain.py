"""
Instruction Chain
~~~~~~~~~~~~~~~~~

Provenance tracking across agent delegation hops.
"""

from __future__ import annotations

from datetime import UTC, datetime

from plyra_guard.core.intent import AgentCall

__all__ = ["InstructionChain"]


class InstructionChain:
    """
    Tracks the full delegation chain in a multi-agent system.

    The chain is append-only — once a hop is added, it cannot be
    removed or modified. This prevents tampering with provenance.
    """

    def __init__(self) -> None:
        self._chain: list[AgentCall] = []
        self._frozen = False

    def add_hop(
        self,
        agent_id: str,
        trust_level: float,
        instruction: str,
    ) -> None:
        """
        Add a new delegation hop to the chain.

        Args:
            agent_id: The agent being delegated to.
            trust_level: The trust score of this agent.
            instruction: The instruction given to the agent.

        Raises:
            RuntimeError: If the chain has been frozen.
        """
        if self._frozen:
            raise RuntimeError("Instruction chain is immutable once frozen")

        self._chain.append(
            AgentCall(
                agent_id=agent_id,
                trust_level=trust_level,
                instruction=instruction,
                timestamp=datetime.now(UTC),
            )
        )

    def freeze(self) -> None:
        """Freeze the chain, making it immutable."""
        self._frozen = True

    @property
    def is_frozen(self) -> bool:
        """Whether the chain is frozen."""
        return self._frozen

    @property
    def chain(self) -> list[AgentCall]:
        """Get the full chain as a list of AgentCall objects."""
        return list(self._chain)

    @property
    def depth(self) -> int:
        """Current delegation depth."""
        return len(self._chain)

    @property
    def effective_trust(self) -> float:
        """
        The effective trust level is the minimum trust in the chain.

        This implements the "weakest link" security model.
        """
        if not self._chain:
            return 1.0
        return min(ac.trust_level for ac in self._chain)

    @property
    def agent_ids(self) -> list[str]:
        """All agent IDs in the chain."""
        return [ac.agent_id for ac in self._chain]

    def has_cycle(self) -> bool:
        """Check if any agent appears more than once in the chain."""
        ids = self.agent_ids
        return len(ids) != len(set(ids))

    def contains_agent(self, agent_id: str) -> bool:
        """Check if a specific agent is in the chain."""
        return agent_id in self.agent_ids

    def to_list(self) -> list[AgentCall]:
        """Export as a list of AgentCall objects."""
        return list(self._chain)
