"""
Configuration Schema
~~~~~~~~~~~~~~~~~~~~

Pydantic models for validating ActionGuard configuration.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "GuardConfig",
    "GlobalConfig",
    "BudgetConfig",
    "RateLimitConfig",
    "PolicyConfig",
    "AgentConfig",
    "EvaluatorConfig",
    "RollbackConfig",
    "ObservabilityConfig",
    "SidecarConfig",
]


class GlobalConfig(BaseModel):
    """Global settings."""

    default_verdict: str = "ALLOW"
    max_risk_score: float = Field(default=0.85, ge=0.0, le=1.0)
    max_delegation_depth: int = Field(default=4, ge=1)
    max_concurrent_delegations: int = Field(default=10, ge=1)


class BudgetConfig(BaseModel):
    """Budget enforcement settings."""

    per_task: float = Field(default=5.00, ge=0.0)
    per_agent_per_run: float = Field(default=1.00, ge=0.0)
    currency: str = "USD"


class RateLimitConfig(BaseModel):
    """Rate limit settings."""

    default: str = "60/min"
    per_tool: dict[str, str] = Field(default_factory=dict)

    @field_validator("default")
    @classmethod
    def validate_default_rate(cls, v: str) -> str:
        """Validate the rate limit format."""
        parts = v.split("/")
        if len(parts) != 2:
            raise ValueError(f"Invalid rate limit format: {v!r}")
        try:
            int(parts[0])
        except ValueError:
            raise ValueError(f"Invalid rate limit count: {parts[0]!r}")
        return v


class PolicyConfig(BaseModel):
    """A single policy rule."""

    name: str
    action_types: list[str] = Field(default_factory=lambda: ["*"])
    condition: str = ""
    verdict: str = "BLOCK"
    message: str = ""
    escalate_to: str | None = None


class AgentConfig(BaseModel):
    """A registered agent's configuration."""

    id: str
    trust_level: float = Field(default=0.5, ge=0.0, le=1.0)
    can_delegate_to: list[str] = Field(default_factory=list)
    max_actions_per_run: int = Field(default=100, ge=1)


class EvaluatorToggles(BaseModel):
    """Per-evaluator enable/disable toggles."""

    enabled: bool = True


class EvaluatorConfig(BaseModel):
    """Evaluator pipeline configuration."""

    schema_validator: EvaluatorToggles = Field(
        default_factory=lambda: EvaluatorToggles(enabled=True)
    )
    policy_engine: EvaluatorToggles = Field(
        default_factory=lambda: EvaluatorToggles(enabled=True)
    )
    risk_scorer: EvaluatorToggles = Field(
        default_factory=lambda: EvaluatorToggles(enabled=True)
    )
    rate_limiter: EvaluatorToggles = Field(
        default_factory=lambda: EvaluatorToggles(enabled=True)
    )
    cost_estimator: EvaluatorToggles = Field(
        default_factory=lambda: EvaluatorToggles(enabled=True)
    )
    human_gate: EvaluatorToggles = Field(
        default_factory=lambda: EvaluatorToggles(enabled=False)
    )


class RollbackConfig(BaseModel):
    """Rollback system configuration."""

    enabled: bool = True
    snapshot_dir: str | None = None
    max_snapshots: int = Field(default=1000, ge=1)


class ObservabilityConfig(BaseModel):
    """Observability configuration."""

    exporters: list[str] = Field(default_factory=lambda: ["stdout"])
    audit_log_max_entries: int = Field(default=10000, ge=100)


class SidecarConfig(BaseModel):
    """HTTP sidecar server configuration."""

    host: str = "0.0.0.0"
    port: int = Field(default=8080, ge=1, le=65535)


class GuardConfig(BaseModel):
    """
    Root configuration model for ActionGuard.

    Validated on load with clear error messages for invalid values.
    """

    version: str = "1.0"
    global_config: GlobalConfig = Field(default_factory=GlobalConfig, alias="global")
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    rate_limits: RateLimitConfig = Field(default_factory=RateLimitConfig)
    policies: list[PolicyConfig] = Field(default_factory=list)
    agents: list[AgentConfig] = Field(default_factory=list)
    evaluators: EvaluatorConfig = Field(default_factory=EvaluatorConfig)
    rollback: RollbackConfig = Field(default_factory=RollbackConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    sidecar: SidecarConfig = Field(default_factory=SidecarConfig)

    model_config = {"populate_by_name": True}
