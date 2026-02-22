# Architecture

## Overview

ActionGuard is structured as a middleware pipeline that sits between an AI agent's decision engine and the actual execution of tools/actions.

```
Agent Decision → Intercept → Evaluate → Execute → Observe → (Rollback)
```

## Core Pipeline

Every action flows through these stages:

### 1. Interception
The `Interceptor` captures function calls (via decorator or adapter) and normalizes them into `ActionIntent` objects — a universal representation of "what the agent wants to do."

### 2. Evaluation
The `EvaluationPipeline` runs a sequence of evaluators. Each returns a verdict:
- **ALLOW** — proceed
- **WARN** — proceed but log a warning
- **ESCALATE** — requires human approval
- **DEFER** — async approval pending
- **BLOCK** — deny outright

A BLOCK verdict short-circuits the remaining evaluators.

### 3. Execution
The `ExecutionGate` runs the actual function with timing, error capture, and parameter sanitization.

### 4. Observation
Every action writes an `AuditEntry` to the audit log and forwards it to configured exporters (stdout, OpenTelemetry, Datadog, webhooks).

### 5. Rollback
If rollback is enabled, the `SnapshotManager` captures pre-execution state. If rollback is requested, the appropriate `RollbackHandler` restores the state.

## Module Structure

```
actionguard/
├── core/           # ActionIntent, Verdict, Guard class, pipeline
├── evaluators/     # 6 built-in evaluators + base class
├── multiagent/     # Trust, delegation, cascade, budgets
├── rollback/       # Snapshots, handlers, coordinator
├── adapters/       # Framework-specific translators
├── observability/  # Audit log, metrics, exporters
├── sidecar/        # HTTP API server
└── config/         # YAML loader, Pydantic schema, defaults
```

## Design Decisions

1. **Framework-agnostic**: Adapters translate from any framework to `ActionIntent`.
2. **Pluggable evaluators**: Add/remove/reorder evaluators at runtime.
3. **Weakest-link trust**: Multi-agent trust = min(trust in chain).
4. **Immutable instruction chains**: Prevent delegation provenance tampering.
5. **Pre-execution snapshots**: Capture state BEFORE action runs for reliable rollback.
