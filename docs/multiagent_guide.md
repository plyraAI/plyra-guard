# Multi-Agent Guide

## Overview

ActionGuard natively supports multi-agent systems with:
- Agent identity and trust management
- Delegation provenance tracking
- Cascade limits (depth, concurrency, cycles)
- Cross-agent budget enforcement
- Cross-agent rollback

## Trust Levels

| Level | Score | Description |
|-------|-------|-------------|
| `HUMAN` | 1.0 | Human operators |
| `ORCHESTRATOR` | 0.8 | Top-level coordinators |
| `PEER` | 0.5 | Same-level collaborators |
| `SUB_AGENT` | 0.3 | Delegated workers |
| `UNKNOWN` | 0.0 | Unregistered agents (blocked by default) |

```python
from actionguard import ActionGuard, TrustLevel

guard = ActionGuard.default()
guard.register_agent("orchestrator", TrustLevel.ORCHESTRATOR)
guard.register_agent("worker-1", TrustLevel.SUB_AGENT)
```

## Trust Modifies Risk Threshold

The effective risk threshold is adjusted by trust:
```
effective_threshold = base_threshold × caller_trust_score
```

A sub-agent (0.3) has a much tighter risk budget than an orchestrator (0.8).

## Instruction Chain

Every `ActionIntent` carries a delegation chain recording every hop:
```python
intent.instruction_chain = [
    AgentCall(agent_id="orchestrator", trust_level=0.8, instruction="Research AI safety"),
    AgentCall(agent_id="research-agent", trust_level=0.5, instruction="Search web"),
]
```

**Effective trust = min(trust in chain)** — weakest link wins.

## Cascade Limits

Configured globally:
```yaml
global:
  max_delegation_depth: 4      # max hops
  max_concurrent_delegations: 10  # parallel actions per orchestrator
```

Cycle detection: if the same agent_id appears twice → BLOCK immediately.

## Cross-Agent Budget

```yaml
budget:
  per_task: 5.00
  per_agent_per_run: 1.00
```

Tracks cumulative cost per task across ALL agents. Detects budget gaming when many cheap sub-agents collectively exceed limits.

## Cross-Agent Rollback

```python
report = guard.rollback_task("task-001")
# Collects all actions across all agents for this task
# Rolls back in reverse chronological order
print(f"Rolled back: {report.rolled_back}")
print(f"Failed: {report.failed}")
```
