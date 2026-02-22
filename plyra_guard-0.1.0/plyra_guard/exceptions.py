"""
ActionGuard Custom Exceptions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

All custom exception classes for ActionGuard, organized by domain.
Every distinct failure mode has its own exception type.

**Structured Error Messages**

All blocking exceptions provide three structured fields:
- ``what_happened``: Clear plain-English description
- ``policy_triggered``: Name of the policy or evaluator
- ``how_to_fix``: Concrete, actionable steps
"""

__all__ = [
    # Base
    "ActionGuardError",
    # Config
    "ConfigError",
    "ConfigFileNotFoundError",
    "ConfigValidationError",
    "ConfigSchemaError",
    # Evaluation
    "EvaluationError",
    "PolicyError",
    "PolicyParseError",
    "PolicyConditionError",
    "RiskScoringError",
    "RateLimitExceededError",
    "BudgetExceededError",
    "HumanApprovalTimeoutError",
    # Execution
    "ExecutionError",
    "ExecutionTimeoutError",
    "ExecutionBlockedError",
    "ActionEscalatedError",
    "ActionDeferredError",
    "TrustViolationError",
    "CascadeDepthExceededError",
    # Rollback
    "RollbackError",
    "RollbackHandlerNotFoundError",
    "SnapshotError",
    "SnapshotNotFoundError",
    "RollbackFailedError",
    # Multi-agent
    "MultiAgentError",
    "AgentNotRegisteredError",
    "TrustLevelError",
    "DelegationDepthExceededError",
    "CycleDetectedError",
    "ConcurrentDelegationExceededError",
    # Adapter
    "AdapterError",
    "AdapterNotFoundError",
    "AdapterWrappingError",
    # Observability
    "ExporterError",
    "AuditLogError",
    # Sidecar
    "SidecarError",
    "SidecarStartupError",
]


# ── Formatting Helper ────────────────────────────────────────────────────────

_SEPARATOR = "─" * 52


def _format_structured_error(
    title: str,
    what_happened: str,
    policy_triggered: str,
    how_to_fix: str,
) -> str:
    """Build a rich, structured error message."""
    lines = [
        f"  {title}",
        f"  {_SEPARATOR}",
        "  What happened:",
        *[f"    {line}" for line in what_happened.strip().splitlines()],
        "",
        "  Policy triggered:",
        f"    {policy_triggered}",
        "",
        "  How to fix:",
        *[f"    {line}" for line in how_to_fix.strip().splitlines()],
    ]
    return "\n".join(lines)


# ── Base Exception ───────────────────────────────────────────────────────────


class ActionGuardError(Exception):
    """Base exception for all ActionGuard errors."""

    def __init__(self, message: str = "", details: dict | None = None) -> None:
        self.details = details or {}
        super().__init__(message)


# ── Config Exceptions ────────────────────────────────────────────────────────


class ConfigError(ActionGuardError):
    """Base exception for configuration-related errors."""


class ConfigFileNotFoundError(ConfigError):
    """Raised when a configuration file cannot be found at the specified path."""


class ConfigValidationError(ConfigError):
    """Raised when configuration values fail validation."""


class ConfigSchemaError(ConfigError):
    """Raised when configuration structure does not match the expected schema."""


# ── Evaluation Exceptions ────────────────────────────────────────────────────


class EvaluationError(ActionGuardError):
    """Base exception for evaluation pipeline errors."""


class PolicyError(EvaluationError):
    """Base exception for policy engine errors."""


class PolicyParseError(PolicyError):
    """Raised when a YAML policy file cannot be parsed."""


class PolicyConditionError(PolicyError):
    """Raised when a policy condition expression is invalid or fails to evaluate."""


class RiskScoringError(EvaluationError):
    """Raised when risk scoring computation fails."""


class RateLimitExceededError(EvaluationError):
    """
    Raised when an agent or tool exceeds its configured rate limit.

    Structured fields:
    - ``what_happened``: description of rate limit breach
    - ``policy_triggered``: the rate limiter evaluator name
    - ``how_to_fix``: actionable remediation steps
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        agent_id: str = "",
        tool_name: str = "",
        limit: str = "",
        details: dict | None = None,
        what_happened: str = "",
        policy_triggered: str = "rate_limiter",
        how_to_fix: str = "",
    ) -> None:
        self.agent_id = agent_id
        self.tool_name = tool_name
        self.limit = limit
        self.what_happened = what_happened or (
            f'Agent "{agent_id}" exceeded rate limit {limit} for tool "{tool_name}".'
        )
        self.policy_triggered = policy_triggered
        self.how_to_fix = how_to_fix or (
            f'1. Reduce call frequency for "{tool_name}" to stay within {limit}\n'
            f"2. Increase the rate limit in your config:\n"
            f"   rate_limits:\n"
            f"     per_tool:\n"
            f'       {tool_name}: "120/min"\n'
            f"3. Add a backoff/retry strategy in your agent logic"
        )
        super().__init__(message, details)

    def __str__(self) -> str:
        return _format_structured_error(
            title=f"RateLimitExceededError: {self.args[0]}",
            what_happened=self.what_happened,
            policy_triggered=self.policy_triggered,
            how_to_fix=self.how_to_fix,
        )


class BudgetExceededError(EvaluationError):
    """
    Raised when an action would exceed the configured budget threshold.

    Structured fields:
    - ``what_happened``: description of budget breach
    - ``policy_triggered``: the cost estimator evaluator name
    - ``how_to_fix``: actionable remediation steps
    """

    def __init__(
        self,
        message: str = "Budget exceeded",
        current_spend: float = 0.0,
        budget_limit: float = 0.0,
        details: dict | None = None,
        what_happened: str = "",
        policy_triggered: str = "cost_estimator",
        how_to_fix: str = "",
    ) -> None:
        self.current_spend = current_spend
        self.budget_limit = budget_limit
        self.what_happened = what_happened or (
            f"Current spend ${current_spend:.2f} would exceed "
            f"the budget limit of ${budget_limit:.2f}."
        )
        self.policy_triggered = policy_triggered
        self.how_to_fix = how_to_fix or (
            f"1. Reduce estimated_cost to stay within"
            f" ${budget_limit:.2f}\n"
            f"2. Increase the budget in your config:\n"
            f"   budget:\n"
            f"     per_task: {budget_limit * 2:.2f}\n"
            f"3. Start a new task context to reset the budget counter"
        )
        super().__init__(message, details)

    def __str__(self) -> str:
        return _format_structured_error(
            title=f"BudgetExceededError: {self.args[0]}",
            what_happened=self.what_happened,
            policy_triggered=self.policy_triggered,
            how_to_fix=self.how_to_fix,
        )


class HumanApprovalTimeoutError(EvaluationError):
    """Raised when human-in-the-loop approval times out."""


# ── Execution Exceptions ─────────────────────────────────────────────────────


class ExecutionError(ActionGuardError):
    """Base exception for action execution errors."""


class ExecutionTimeoutError(ExecutionError):
    """Raised when an action execution exceeds its timeout."""


class ExecutionBlockedError(ExecutionError):
    """
    Raised when an action is blocked by the evaluation pipeline.

    Structured fields:
    - ``what_happened``: clear description of what was blocked and why
    - ``policy_triggered``: the policy or evaluator that caused the block
    - ``how_to_fix``: concrete, actionable remediation steps
    """

    def __init__(
        self,
        message: str = "Action blocked",
        verdict: str = "BLOCK",
        reason: str = "",
        details: dict | None = None,
        what_happened: str = "",
        policy_triggered: str = "",
        how_to_fix: str = "",
    ) -> None:
        self.verdict = verdict
        self.reason = reason
        self.what_happened = what_happened or reason or message
        self.policy_triggered = policy_triggered
        self.how_to_fix = how_to_fix or (
            "1. Check the action parameters against your policy conditions\n"
            "2. Modify or remove the blocking policy in your config\n"
            "3. Use guard.explain(intent) for a detailed breakdown"
        )
        super().__init__(message, details)

    def __str__(self) -> str:
        return _format_structured_error(
            title=f"ExecutionBlockedError: {self.args[0]}",
            what_happened=self.what_happened,
            policy_triggered=self.policy_triggered or "(unknown)",
            how_to_fix=self.how_to_fix,
        )


class ActionEscalatedError(ExecutionError):
    """
    Raised when an action requires escalation to a human or higher-trust agent.

    Structured fields:
    - ``what_happened``: description of why escalation is required
    - ``policy_triggered``: the policy or evaluator that escalated
    - ``how_to_fix``: how to handle or bypass escalation
    """

    def __init__(
        self,
        message: str = "Action escalated",
        reason: str = "",
        escalate_to: str = "human",
        details: dict | None = None,
        what_happened: str = "",
        policy_triggered: str = "",
        how_to_fix: str = "",
    ) -> None:
        self.reason = reason
        self.escalate_to = escalate_to
        self.what_happened = what_happened or (
            f"Action requires escalation to {escalate_to}. {reason}"
        )
        self.policy_triggered = policy_triggered
        self.how_to_fix = how_to_fix or (
            f"1. Have a {escalate_to}-level agent or human approve this action\n"
            f"2. Increase the agent's trust level in your config\n"
            f"3. Downgrade the policy verdict from ESCALATE to WARN"
        )
        super().__init__(message, details)

    def __str__(self) -> str:
        return _format_structured_error(
            title=f"ActionEscalatedError: {self.args[0]}",
            what_happened=self.what_happened,
            policy_triggered=self.policy_triggered or "(unknown)",
            how_to_fix=self.how_to_fix,
        )


class ActionDeferredError(ExecutionError):
    """
    Raised when an action is deferred for later execution.

    Structured fields:
    - ``what_happened``: description of deferral
    - ``policy_triggered``: the policy or evaluator that deferred
    - ``how_to_fix``: how to handle deferral
    """

    def __init__(
        self,
        message: str = "Action deferred",
        reason: str = "",
        defer_seconds: int = 60,
        details: dict | None = None,
        what_happened: str = "",
        policy_triggered: str = "",
        how_to_fix: str = "",
    ) -> None:
        self.reason = reason
        self.defer_seconds = defer_seconds
        self.what_happened = what_happened or (
            f"Action deferred for {defer_seconds}s. {reason}"
        )
        self.policy_triggered = policy_triggered
        self.how_to_fix = how_to_fix or (
            f"1. Retry this action after {defer_seconds} seconds\n"
            f"2. Remove or reduce the deferral policy in your config\n"
            f"3. Use guard.override(action_id, reason='...') to bypass"
        )
        super().__init__(message, details)

    def __str__(self) -> str:
        return _format_structured_error(
            title=f"ActionDeferredError: {self.args[0]}",
            what_happened=self.what_happened,
            policy_triggered=self.policy_triggered or "(unknown)",
            how_to_fix=self.how_to_fix,
        )


class TrustViolationError(ExecutionError):
    """
    Raised when an agent's action violates trust level restrictions.

    Structured fields:
    - ``what_happened``: description of trust violation
    - ``policy_triggered``: the trust evaluator or ledger
    - ``how_to_fix``: how to resolve the trust issue
    """

    def __init__(
        self,
        message: str = "Trust violation",
        agent_id: str = "",
        required_trust: str = "",
        actual_trust: str = "",
        details: dict | None = None,
        what_happened: str = "",
        policy_triggered: str = "trust_ledger",
        how_to_fix: str = "",
    ) -> None:
        self.agent_id = agent_id
        self.required_trust = required_trust
        self.actual_trust = actual_trust
        self.what_happened = what_happened or (
            f'Agent "{agent_id}" has trust level {actual_trust} '
            f"but this action requires {required_trust}."
        )
        self.policy_triggered = policy_triggered
        self.how_to_fix = how_to_fix or (
            f'1. Register agent "{agent_id}" with a higher trust level:\n'
            f'   guard.register_agent("{agent_id}", TrustLevel.ORCHESTRATOR)\n'
            f"2. Delegate this action to a higher-trust agent\n"
            f"3. Lower the trust requirement in your policy configuration"
        )
        super().__init__(message, details)

    def __str__(self) -> str:
        return _format_structured_error(
            title=f"TrustViolationError: {self.args[0]}",
            what_happened=self.what_happened,
            policy_triggered=self.policy_triggered,
            how_to_fix=self.how_to_fix,
        )


class CascadeDepthExceededError(ExecutionError):
    """
    Raised when an agent delegation chain exceeds the max depth.

    Structured fields:
    - ``what_happened``: description of cascade breach
    - ``policy_triggered``: the cascade controller
    - ``how_to_fix``: how to reduce delegation depth
    """

    def __init__(
        self,
        message: str = "Cascade depth exceeded",
        current_depth: int = 0,
        max_depth: int = 4,
        details: dict | None = None,
        what_happened: str = "",
        policy_triggered: str = "cascade_controller",
        how_to_fix: str = "",
    ) -> None:
        self.current_depth = current_depth
        self.max_depth = max_depth
        self.what_happened = what_happened or (
            f"Delegation chain has depth {current_depth}, "
            f"exceeding the limit of {max_depth}."
        )
        self.policy_triggered = policy_triggered
        self.how_to_fix = how_to_fix or (
            f"1. Flatten your agent hierarchy to stay within depth {max_depth}\n"
            f"2. Increase max_delegation_depth in your config:\n"
            f"   global:\n"
            f"     max_delegation_depth: {max_depth + 2}\n"
            f"3. Use direct execution instead of delegation for leaf actions"
        )
        super().__init__(message, details)

    def __str__(self) -> str:
        return _format_structured_error(
            title=f"CascadeDepthExceededError: {self.args[0]}",
            what_happened=self.what_happened,
            policy_triggered=self.policy_triggered,
            how_to_fix=self.how_to_fix,
        )


# ── Rollback Exceptions ──────────────────────────────────────────────────────


class RollbackError(ActionGuardError):
    """Base exception for rollback errors."""


class RollbackHandlerNotFoundError(RollbackError):
    """Raised when no rollback handler is registered for an action type."""


class SnapshotError(RollbackError):
    """Base exception for snapshot errors."""


class SnapshotNotFoundError(SnapshotError):
    """Raised when a snapshot for a given action_id cannot be found."""


class RollbackFailedError(RollbackError):
    """Raised when a rollback operation fails to restore state."""


# ── Multi-agent Exceptions ───────────────────────────────────────────────────


class MultiAgentError(ActionGuardError):
    """Base exception for multi-agent system errors."""


class AgentNotRegisteredError(MultiAgentError):
    """Raised when an action references an unregistered agent_id."""


class TrustLevelError(MultiAgentError):
    """Raised when trust level validation fails."""


class DelegationDepthExceededError(MultiAgentError):
    """Raised when the instruction chain exceeds max_delegation_depth."""


class CycleDetectedError(MultiAgentError):
    """Raised when a cycle is detected in the agent delegation chain."""


class ConcurrentDelegationExceededError(MultiAgentError):
    """Raised when an orchestrator exceeds max_concurrent_delegations."""


# ── Adapter Exceptions ───────────────────────────────────────────────────────


class AdapterError(ActionGuardError):
    """Base exception for adapter errors."""


class AdapterNotFoundError(AdapterError):
    """Raised when no adapter can handle the given tool type."""


class AdapterWrappingError(AdapterError):
    """Raised when wrapping a tool in an adapter fails."""


# ── Observability Exceptions ─────────────────────────────────────────────────


class ExporterError(ActionGuardError):
    """Base exception for exporter errors."""


class AuditLogError(ActionGuardError):
    """Raised when writing to the audit log fails."""


# ── Sidecar Exceptions ───────────────────────────────────────────────────────


class SidecarError(ActionGuardError):
    """Base exception for HTTP sidecar server errors."""


class SidecarStartupError(SidecarError):
    """Raised when the sidecar server fails to start."""
