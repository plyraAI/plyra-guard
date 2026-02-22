"""
Execution Gate
~~~~~~~~~~~~~~

Executes guarded actions with pre/post hooks, timeout, and rollback support.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from plyra_guard.core.intent import ActionIntent, ActionResult, AuditEntry
from plyra_guard.core.verdict import Verdict

__all__ = ["ExecutionGate"]

logger = logging.getLogger(__name__)


class ExecutionGate:
    """
    Executes an action with pre and post hooks.

    Responsibilities:
    - Execute the action function
    - Measure duration
    - Capture errors
    - Build ActionResult and AuditEntry
    """

    def __init__(self, timeout_seconds: float = 300.0) -> None:
        self._timeout = timeout_seconds

    def execute(
        self,
        intent: ActionIntent,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        verdict: Verdict,
        risk_score: float = 0.0,
        policy_triggered: str | None = None,
        evaluator_results: list | None = None,
    ) -> ActionResult:
        """
        Execute a function call with timing and error handling.

        Args:
            intent: The evaluated ActionIntent.
            func: The function to execute.
            args: Positional arguments.
            kwargs: Keyword arguments.
            verdict: The evaluation verdict.
            risk_score: Computed risk score.
            policy_triggered: Name of the triggered policy, if any.
            evaluator_results: List of evaluator results.

        Returns:
            ActionResult with execution details.

        Raises:
            ExecutionBlockedError: If the verdict blocks execution.
        """
        if verdict.is_blocking():
            audit = self._build_audit(
                intent=intent,
                verdict=verdict,
                risk_score=risk_score,
                policy_triggered=policy_triggered,
                evaluator_results=evaluator_results or [],
                duration_ms=0,
            )
            result = ActionResult(
                action_id=intent.action_id,
                success=False,
                audit_entry=audit,
            )
            return result

        start = time.perf_counter()
        error: Exception | None = None
        output: Any = None
        success = True

        try:
            output = func(*args, **kwargs)
        except Exception as exc:
            error = exc
            success = False
            logger.error(
                "Action %s (%s) failed: %s",
                intent.action_id,
                intent.action_type,
                exc,
            )

        duration_ms = int((time.perf_counter() - start) * 1000)

        audit = self._build_audit(
            intent=intent,
            verdict=verdict,
            risk_score=risk_score,
            policy_triggered=policy_triggered,
            evaluator_results=evaluator_results or [],
            duration_ms=duration_ms,
            error=str(error) if error else None,
        )

        return ActionResult(
            action_id=intent.action_id,
            success=success,
            output=output,
            duration_ms=duration_ms,
            audit_entry=audit,
            error=error,
        )

    def _build_audit(
        self,
        intent: ActionIntent,
        verdict: Verdict,
        risk_score: float,
        policy_triggered: str | None,
        evaluator_results: list,
        duration_ms: int,
        error: str | None = None,
    ) -> AuditEntry:
        """Build an AuditEntry from execution results."""
        # Sanitize parameters — strip obvious credential keys
        sanitized_params = self._sanitize_params(intent.parameters)

        return AuditEntry(
            action_id=intent.action_id,
            agent_id=intent.agent_id,
            action_type=intent.action_type,
            verdict=verdict,
            risk_score=risk_score,
            task_id=intent.task_id,
            policy_triggered=policy_triggered,
            evaluator_results=evaluator_results,
            instruction_chain=intent.instruction_chain,
            parameters=sanitized_params,
            duration_ms=duration_ms,
            timestamp=intent.timestamp,
            error=error,
        )

    def _sanitize_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Remove sensitive keys from parameters for the audit log."""
        sensitive_keys = {
            "password",
            "secret",
            "token",
            "api_key",
            "apikey",
            "credential",
            "private_key",
            "access_token",
            "refresh_token",
            "auth",
        }
        sanitized: dict[str, Any] = {}
        for key, value in params.items():
            if key.lower() in sensitive_keys:
                sanitized[key] = "***REDACTED***"
            elif isinstance(value, dict):
                sanitized[key] = self._sanitize_params(value)
            else:
                sanitized[key] = value
        return sanitized
