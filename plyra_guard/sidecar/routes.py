"""
Sidecar Routes
~~~~~~~~~~~~~~

FastAPI route handlers for the HTTP sidecar server.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING, Any

from plyra_guard.core.intent import ActionIntent, AuditFilter
from plyra_guard.core.verdict import RiskLevel, Verdict
from plyra_guard.sidecar.models import (
    EvaluateRequest,
    EvaluateResponse,
    ExecuteRequest,
    ExecuteResponse,
    HealthResponse,
    RollbackRequest,
    RollbackResponse,
)

if TYPE_CHECKING:
    from plyra_guard.core.guard import ActionGuard

__all__ = ["register_routes"]


def register_routes(app: Any, guard: ActionGuard) -> None:
    """Register all sidecar routes on the FastAPI app."""
    from fastapi import HTTPException, Query

    _uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}"
        r"-[0-9a-f]{4}-[0-9a-f]{12}$",
        re.IGNORECASE,
    )

    # Store pending evaluations for execute endpoint
    _pending: dict[str, ActionIntent] = {}

    @app.post("/evaluate", response_model=EvaluateResponse)
    async def evaluate_action(req: EvaluateRequest) -> EvaluateResponse:
        """Evaluate an action without executing it."""
        intent = ActionIntent(
            action_type=req.action_type,
            tool_name=req.tool_name or req.action_type,
            parameters=req.parameters,
            agent_id=req.agent_id,
            task_id=req.task_id,
            task_context=req.task_context,
            estimated_cost=req.estimated_cost,
            risk_level=RiskLevel.MEDIUM,
        )

        result = guard.evaluate(intent)

        # Store for potential execution
        _pending[intent.action_id] = intent

        # Extract risk score
        risk_score = result.metadata.get("risk_score", 0.0)
        policy_triggered = result.metadata.get("policy_name")

        return EvaluateResponse(
            verdict=result.verdict.value,
            reason=result.reason,
            risk_score=risk_score,
            policy_triggered=policy_triggered,
            action_id=intent.action_id,
            confidence=result.confidence,
        )

    @app.post("/execute", response_model=ExecuteResponse)
    async def execute_action(req: ExecuteRequest) -> ExecuteResponse:
        """Execute a previously evaluated action."""
        if req.action_id not in _pending:
            return ExecuteResponse(
                success=False,
                output="Action not found or not yet evaluated",
            )
        # In sidecar mode, we can't execute arbitrary functions.
        # This endpoint acknowledges the action.
        _pending.pop(req.action_id, None)
        return ExecuteResponse(
            success=True,
            output="Action acknowledged (sidecar mode)",
            duration_ms=0,
        )

    @app.post("/rollback", response_model=RollbackResponse)
    async def rollback_action(req: RollbackRequest) -> RollbackResponse:
        """Rollback action(s)."""
        if req.action_id and not _uuid_pattern.match(req.action_id):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action ID format: {req.action_id}",
            )

        rolled_back: list[str] = []
        failed: list[str] = []

        if req.action_id:
            success = guard.rollback(req.action_id)
            if success:
                rolled_back.append(req.action_id)
            else:
                failed.append(req.action_id)

        elif req.task_id:
            report = guard.rollback_task(req.task_id)
            rolled_back = report.rolled_back
            failed = report.failed

        elif req.last_n:
            results = guard.rollback_last(req.last_n)
            for i, success in enumerate(results):
                aid = f"action_{i}"
                if success:
                    rolled_back.append(aid)
                else:
                    failed.append(aid)

        return RollbackResponse(rolled_back=rolled_back, failed=failed)

    @app.get("/audit")
    async def get_audit(
        agent_id: str | None = Query(None),
        task_id: str | None = Query(None),
        verdict: str | None = Query(None),
        from_time: str | None = Query(None),
        to_time: str | None = Query(None),
        limit: int = Query(100),
    ) -> dict[str, list[dict]]:
        """Query the audit log."""
        audit_filter = AuditFilter(
            agent_id=agent_id,
            task_id=task_id,
            verdict=Verdict(verdict) if verdict else None,
            from_time=(datetime.fromisoformat(from_time) if from_time else None),
            to_time=(datetime.fromisoformat(to_time) if to_time else None),
            limit=limit,
        )

        entries = guard.get_audit_log(filters=audit_filter)
        return {"entries": [e.to_dict() for e in entries]}

    @app.get("/metrics")
    async def get_metrics() -> str:
        """Get Prometheus-format metrics."""
        metrics = guard.get_metrics()
        return metrics.to_prometheus()

    @app.get("/health", response_model=HealthResponse)
    async def health_check() -> HealthResponse:
        """Health check endpoint."""
        return HealthResponse(status="ok", version="0.1.0")
