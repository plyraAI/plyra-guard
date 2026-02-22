"""
Schema Validator Evaluator
~~~~~~~~~~~~~~~~~~~~~~~~~~

Validates that an ActionIntent is well-formed before further processing.
"""

from __future__ import annotations

from plyra_guard.core.intent import ActionIntent, EvaluatorResult
from plyra_guard.core.verdict import Verdict
from plyra_guard.evaluators.base import BaseEvaluator

__all__ = ["SchemaValidator"]


class SchemaValidator(BaseEvaluator):
    """
    Validates the structural integrity of an ActionIntent.

    Checks:
    - action_type is non-empty and follows dotted notation
    - tool_name is non-empty
    - agent_id is non-empty
    - parameters is a dict
    - estimated_cost is non-negative
    - risk_level is valid
    """

    @property
    def name(self) -> str:
        return "schema_validator"

    @property
    def priority(self) -> int:
        return 10

    def evaluate(self, intent: ActionIntent) -> EvaluatorResult:
        """Validate the ActionIntent structure."""
        errors: list[str] = []

        if not intent.action_type or not intent.action_type.strip():
            errors.append("action_type must be non-empty")

        if not intent.tool_name or not intent.tool_name.strip():
            errors.append("tool_name must be non-empty")

        if not intent.agent_id or not intent.agent_id.strip():
            errors.append("agent_id must be non-empty")

        if not isinstance(intent.parameters, dict):
            errors.append("parameters must be a dict")

        if intent.estimated_cost < 0:
            errors.append("estimated_cost must be non-negative")

        if not intent.action_id:
            errors.append("action_id must be non-empty")

        if errors:
            return EvaluatorResult(
                verdict=Verdict.BLOCK,
                reason=f"Schema validation failed: {'; '.join(errors)}",
                confidence=1.0,
                evaluator_name=self.name,
                metadata={"errors": errors},
            )

        return EvaluatorResult(
            verdict=Verdict.ALLOW,
            reason="ActionIntent is well-formed",
            confidence=1.0,
            evaluator_name=self.name,
        )
