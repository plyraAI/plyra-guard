"""
ActionGuard Verdict & Risk Level Enums
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Core enums that define the possible outcomes of evaluation
and the severity levels for actions.
"""

from enum import StrEnum

__all__ = ["Verdict", "RiskLevel", "TrustLevel"]


class Verdict(StrEnum):
    """
    Result of evaluating an ActionIntent.

    - ALLOW: Action may proceed without restrictions.
    - BLOCK: Action is denied outright.
    - ESCALATE: Action requires higher authority or human approval.
    - DEFER: Evaluation is deferred (e.g., async approval pending).
    - WARN: Action may proceed, but a warning is logged.
    """

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"
    DEFER = "DEFER"
    WARN = "WARN"

    def is_permissive(self) -> bool:
        """Return True if this verdict allows the action to proceed."""
        return self in (Verdict.ALLOW, Verdict.WARN)

    def is_blocking(self) -> bool:
        """Return True if this verdict stops execution."""
        return self in (Verdict.BLOCK, Verdict.ESCALATE, Verdict.DEFER)


class RiskLevel(StrEnum):
    """
    Pre-declared risk classification for an action type.

    Used as the initial baseline before dynamic risk scoring adjusts it.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

    def base_score(self) -> float:
        """Return the base risk score for this risk level."""
        return {
            RiskLevel.LOW: 0.1,
            RiskLevel.MEDIUM: 0.3,
            RiskLevel.HIGH: 0.6,
            RiskLevel.CRITICAL: 0.9,
        }[self]


class TrustLevel(StrEnum):
    """
    Trust classification for agents in a multi-agent system.

    Determines what risk thresholds apply and what actions are permitted.
    """

    HUMAN = "HUMAN"
    ORCHESTRATOR = "ORCHESTRATOR"
    PEER = "PEER"
    SUB_AGENT = "SUB_AGENT"
    UNKNOWN = "UNKNOWN"

    def score(self) -> float:
        """Return the numeric trust score for this level."""
        return {
            TrustLevel.HUMAN: 1.0,
            TrustLevel.ORCHESTRATOR: 0.8,
            TrustLevel.PEER: 0.5,
            TrustLevel.SUB_AGENT: 0.3,
            TrustLevel.UNKNOWN: 0.0,
        }[self]
