"""
Sidecar Pydantic Models
~~~~~~~~~~~~~~~~~~~~~~~

Request/response models for the HTTP sidecar endpoints.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "EvaluateRequest",
    "EvaluateResponse",
    "ExecuteRequest",
    "ExecuteResponse",
    "RollbackRequest",
    "RollbackResponse",
    "AuditEntryResponse",
    "AuditQueryParams",
    "HealthResponse",
]


class EvaluateRequest(BaseModel):
    """Request body for POST /evaluate."""

    action_type: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    agent_id: str = "default"
    task_id: str | None = None
    task_context: str = ""
    estimated_cost: float = 0.0
    tool_name: str = ""


class EvaluateResponse(BaseModel):
    """Response for POST /evaluate."""

    verdict: str
    reason: str
    risk_score: float = 0.0
    policy_triggered: str | None = None
    action_id: str = ""
    confidence: float = 1.0


class ExecuteRequest(BaseModel):
    """Request body for POST /execute."""

    action_id: str


class ExecuteResponse(BaseModel):
    """Response for POST /execute."""

    success: bool
    output: Any = None
    duration_ms: int = 0


class RollbackRequest(BaseModel):
    """Request body for POST /rollback."""

    action_id: str | None = None
    task_id: str | None = None
    last_n: int | None = None


class RollbackResponse(BaseModel):
    """Response for POST /rollback."""

    rolled_back: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)


class AuditEntryResponse(BaseModel):
    """A single audit entry in the GET /audit response."""

    action_id: str
    agent_id: str
    action_type: str
    verdict: str
    risk_score: float = 0.0
    task_id: str | None = None
    policy_triggered: str | None = None
    duration_ms: int = 0
    timestamp: str = ""
    rolled_back: bool = False
    error: str | None = None


class AuditQueryParams(BaseModel):
    """Query parameters for GET /audit."""

    agent_id: str | None = None
    task_id: str | None = None
    verdict: str | None = None
    from_time: str | None = None
    to_time: str | None = None
    limit: int = 100


class HealthResponse(BaseModel):
    """Response for GET /health."""

    status: str = "ok"
    version: str = "0.1.0"
