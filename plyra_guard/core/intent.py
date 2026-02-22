"""
ActionGuard Intent & Result Data Models
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Defines the core dataclasses that flow through the evaluation pipeline:
ActionIntent (input), ActionResult (output), and supporting types.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from plyra_guard.core.verdict import RiskLevel, Verdict

__all__ = [
    "AgentCall",
    "ActionIntent",
    "ActionResult",
    "AuditEntry",
    "AuditFilter",
    "EvaluatorResult",
    "RollbackReport",
    "GuardMetrics",
]


@dataclass(frozen=True)
class AgentCall:
    """
    One hop in a multi-agent delegation chain.

    Attributes:
        agent_id: Unique identifier of the agent making the call.
        trust_level: Numeric trust score of this agent (0.0-1.0).
        instruction: The instruction given to this agent.
        timestamp: When this delegation occurred.
    """

    agent_id: str
    trust_level: float
    instruction: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ActionIntent:
    """
    Represents a pending action that an agent wants to execute.

    This is the primary data structure that flows through the ActionGuard
    evaluation pipeline. It captures everything needed to decide whether
    an action should be allowed, blocked, or escalated.

    Attributes:
        action_type: Hierarchical action descriptor, e.g. "file.delete".
        tool_name: The name of the tool being invoked.
        parameters: Arguments to the tool call.
        agent_id: Identity of the calling agent.
        task_context: Human-readable description of what the agent is doing.
        action_id: Unique ID for this intent (auto-generated).
        task_id: Optional task grouping for multi-step workflows.
        timestamp: When the intent was created.
        estimated_cost: Estimated monetary cost in USD.
        risk_level: Pre-declared risk classification.
        instruction_chain: Full delegation chain for multi-agent provenance.
        metadata: Arbitrary metadata bag for extensibility.
    """

    action_type: str
    tool_name: str
    parameters: dict[str, Any]
    agent_id: str
    task_context: str = ""
    action_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    estimated_cost: float = 0.0
    risk_level: RiskLevel = RiskLevel.MEDIUM
    instruction_chain: list[AgentCall] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluatorResult:
    """
    The output of a single evaluator in the pipeline.

    Attributes:
        verdict: The evaluator's decision.
        reason: Human-readable explanation.
        confidence: How confident the evaluator is (0.0-1.0).
        evaluator_name: Name of the evaluator class.
        suggested_action: Optional suggestion for remediation.
        metadata: Arbitrary metadata.
    """

    verdict: Verdict
    reason: str
    confidence: float = 1.0
    evaluator_name: str = ""
    suggested_action: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    """
    The result of executing a guarded action.

    Attributes:
        action_id: Matches the originating ActionIntent.
        success: Whether execution completed without error.
        output: The return value from the tool.
        duration_ms: Wall-clock execution time in milliseconds.
        rolled_back: Whether this action was subsequently rolled back.
        audit_entry: The full audit record for this action.
        error: The exception, if any, that occurred during execution.
    """

    action_id: str
    success: bool
    output: Any = None
    duration_ms: int = 0
    rolled_back: bool = False
    audit_entry: AuditEntry | None = None
    error: Exception | None = None


@dataclass
class AuditEntry:
    """
    Immutable audit record written for every action evaluated by ActionGuard.

    Stored in the audit log and forwarded to all configured exporters.
    """

    action_id: str
    agent_id: str
    action_type: str
    verdict: Verdict
    risk_score: float = 0.0
    task_id: str | None = None
    policy_triggered: str | None = None
    evaluator_results: list[EvaluatorResult] = field(default_factory=list)
    instruction_chain: list[AgentCall] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    rolled_back: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "action_id": self.action_id,
            "agent_id": self.agent_id,
            "action_type": self.action_type,
            "verdict": self.verdict.value,
            "risk_score": self.risk_score,
            "task_id": self.task_id,
            "policy_triggered": self.policy_triggered,
            "evaluator_results": [
                {
                    "verdict": er.verdict.value,
                    "reason": er.reason,
                    "confidence": er.confidence,
                    "evaluator_name": er.evaluator_name,
                }
                for er in self.evaluator_results
            ],
            "instruction_chain": [
                {
                    "agent_id": ac.agent_id,
                    "trust_level": ac.trust_level,
                    "instruction": ac.instruction,
                    "timestamp": ac.timestamp.isoformat(),
                }
                for ac in self.instruction_chain
            ],
            "parameters": self.parameters,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
            "rolled_back": self.rolled_back,
            "error": self.error,
        }


@dataclass
class AuditFilter:
    """Filter criteria for querying the audit log."""

    agent_id: str | None = None
    task_id: str | None = None
    verdict: Verdict | None = None
    action_type: str | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    limit: int = 100


@dataclass
class RollbackReport:
    """Summary of a batch rollback operation (e.g., rollback_task)."""

    task_id: str
    total_actions: int = 0
    rolled_back: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        """Return True if all actions were successfully rolled back."""
        return len(self.failed) == 0 and len(self.rolled_back) > 0


@dataclass
class GuardMetrics:
    """Prometheus-style metrics snapshot."""

    total_actions: int = 0
    allowed_actions: int = 0
    blocked_actions: int = 0
    escalated_actions: int = 0
    warned_actions: int = 0
    deferred_actions: int = 0
    rollbacks: int = 0
    rollback_failures: int = 0
    total_cost: float = 0.0
    avg_risk_score: float = 0.0
    avg_duration_ms: float = 0.0
    actions_by_agent: dict[str, int] = field(default_factory=dict)
    actions_by_type: dict[str, int] = field(default_factory=dict)
    verdicts_by_policy: dict[str, int] = field(default_factory=dict)

    def to_prometheus(self) -> str:
        """Render as Prometheus text exposition format."""
        lines: list[str] = [
            f"plyra_guard_total_actions {self.total_actions}",
            f"plyra_guard_allowed_actions {self.allowed_actions}",
            f"plyra_guard_blocked_actions {self.blocked_actions}",
            f"plyra_guard_escalated_actions {self.escalated_actions}",
            f"plyra_guard_warned_actions {self.warned_actions}",
            f"plyra_guard_deferred_actions {self.deferred_actions}",
            f"plyra_guard_rollbacks {self.rollbacks}",
            f"plyra_guard_rollback_failures {self.rollback_failures}",
            f"plyra_guard_total_cost {self.total_cost}",
            f"plyra_guard_avg_risk_score {self.avg_risk_score}",
            f"plyra_guard_avg_duration_ms {self.avg_duration_ms}",
        ]
        for agent_id, count in self.actions_by_agent.items():
            lines.append(
                f'plyra_guard_actions_by_agent{{agent_id="{agent_id}"}} {count}'
            )
        for action_type, count in self.actions_by_type.items():
            lines.append(
                f'plyra_guard_actions_by_type{{action_type="{action_type}"}} {count}'
            )
        return "\n".join(lines) + "\n"
