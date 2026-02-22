# API Reference

## ActionGuard

The main class. All operations go through here.

### Constructors

```python
# From YAML config file
guard = ActionGuard.from_config("guard_config.yaml")

# With sensible defaults (no config needed)
guard = ActionGuard.default()
```

### Protection

```python
# Decorator
@guard.protect(action_type, risk_level=RiskLevel.MEDIUM, rollback=True, tags=[])
def my_function(...): ...

# Wrap framework tools
wrapped_tools = guard.wrap(tools: list[Any]) -> list[Any]

# Evaluate without executing (dry-run)
result = guard.evaluate(intent: ActionIntent) -> EvaluatorResult
```

### Rollback

```python
guard.rollback(action_id: str) -> bool
guard.rollback_last(n: int = 1, agent_id: str | None = None) -> list[bool]
guard.rollback_task(task_id: str) -> RollbackReport
```

### Multi-Agent

```python
guard.register_agent(agent_id: str, trust_level: TrustLevel) -> None

with guard.set_task_context(task_id: str, agent_id: str):
    # Actions here use this task/agent context
    ...
```

### Observability

```python
guard.add_exporter(exporter) -> None
guard.get_audit_log(filters: AuditFilter | None) -> list[AuditEntry]
guard.get_metrics() -> GuardMetrics
```

### Sidecar

```python
guard.serve(host="0.0.0.0", port=8080) -> None
```

---

## Data Models

### ActionIntent
```python
@dataclass
class ActionIntent:
    action_type: str          # e.g. "file.delete"
    tool_name: str            # e.g. "delete_file"
    parameters: dict          # tool arguments
    agent_id: str             # calling agent
    task_context: str         # what the agent is doing
    action_id: str            # auto-generated UUID
    task_id: str | None       # task grouping
    timestamp: datetime       # auto-set
    estimated_cost: float     # in USD
    risk_level: RiskLevel     # LOW, MEDIUM, HIGH, CRITICAL
    instruction_chain: list[AgentCall]  # delegation provenance
    metadata: dict            # extensibility
```

### EvaluatorResult
```python
@dataclass
class EvaluatorResult:
    verdict: Verdict          # ALLOW, BLOCK, ESCALATE, DEFER, WARN
    reason: str               # explanation
    confidence: float         # 0.0-1.0
    evaluator_name: str
    suggested_action: str | None
    metadata: dict
```

### AuditEntry
```python
@dataclass
class AuditEntry:
    action_id: str
    agent_id: str
    action_type: str
    verdict: Verdict
    risk_score: float
    task_id: str | None
    policy_triggered: str | None
    evaluator_results: list[EvaluatorResult]
    instruction_chain: list[AgentCall]
    parameters: dict          # sanitized
    duration_ms: int
    timestamp: datetime
    rolled_back: bool
    error: str | None
```

---

## Enums

### Verdict
`ALLOW`, `BLOCK`, `ESCALATE`, `DEFER`, `WARN`

### RiskLevel
`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`

### TrustLevel
`HUMAN` (1.0), `ORCHESTRATOR` (0.8), `PEER` (0.5), `SUB_AGENT` (0.3), `UNKNOWN` (0.0)
