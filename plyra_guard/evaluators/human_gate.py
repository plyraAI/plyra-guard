"""
Human Gate Evaluator
~~~~~~~~~~~~~~~~~~~~

Human-in-the-loop approval gate. When triggered, pauses the pipeline
and requests human approval via a configurable callback.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from plyra_guard.core.intent import ActionIntent, EvaluatorResult
from plyra_guard.core.verdict import RiskLevel, Verdict
from plyra_guard.evaluators.base import BaseEvaluator

__all__ = ["HumanGate"]

logger = logging.getLogger(__name__)


def _default_approval_callback(intent: ActionIntent) -> bool:
    """Default callback that auto-approves (for non-interactive use)."""
    logger.warning(
        "HumanGate: Auto-approving action '%s' (no callback configured)",
        intent.action_type,
    )
    return True


class HumanGate(BaseEvaluator):
    """
    Requests human approval for high-risk or policy-triggered actions.

    The approval mechanism is pluggable via a callback function.
    In production, this might integrate with Slack, email, or a web UI.

    Args:
        approval_callback: A callable that takes an ActionIntent and returns
            True (approved) or False (denied).
        require_for_risk_levels: Risk levels that always require human approval.
        require_for_action_types: Action types that require human approval.
        enabled: Whether this gate is active.
    """

    def __init__(
        self,
        approval_callback: Callable[[ActionIntent], bool] | None = None,
        require_for_risk_levels: list[RiskLevel] | None = None,
        require_for_action_types: list[str] | None = None,
        enabled: bool = False,
    ) -> None:
        self._callback = approval_callback or _default_approval_callback
        self._require_risk_levels = require_for_risk_levels or [
            RiskLevel.CRITICAL,
        ]
        self._require_action_types = require_for_action_types or []
        self._enabled = enabled
        self._approval_log: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return "human_gate"

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def priority(self) -> int:
        return 60

    def _requires_approval(self, intent: ActionIntent) -> bool:
        """Determine if this intent needs human approval."""
        if intent.risk_level in self._require_risk_levels:
            return True
        if intent.action_type in self._require_action_types:
            return True
        return False

    def evaluate(self, intent: ActionIntent) -> EvaluatorResult:
        """Check if human approval is needed and request it."""
        if not self._requires_approval(intent):
            return EvaluatorResult(
                verdict=Verdict.ALLOW,
                reason="Human approval not required",
                confidence=1.0,
                evaluator_name=self.name,
            )

        # Request approval
        logger.info(
            "HumanGate: Requesting approval for action '%s' (risk=%s, agent=%s)",
            intent.action_type,
            intent.risk_level.value,
            intent.agent_id,
        )

        try:
            approved = self._callback(intent)
        except Exception as exc:
            logger.error("HumanGate: Approval callback failed: %s", exc)
            return EvaluatorResult(
                verdict=Verdict.BLOCK,
                reason=f"Human approval callback failed: {exc}",
                confidence=1.0,
                evaluator_name=self.name,
            )

        self._approval_log.append(
            {
                "action_id": intent.action_id,
                "action_type": intent.action_type,
                "agent_id": intent.agent_id,
                "approved": approved,
            }
        )

        if approved:
            return EvaluatorResult(
                verdict=Verdict.ALLOW,
                reason="Human approved this action",
                confidence=1.0,
                evaluator_name=self.name,
            )

        return EvaluatorResult(
            verdict=Verdict.BLOCK,
            reason="Human denied this action",
            confidence=1.0,
            evaluator_name=self.name,
        )
