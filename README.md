<p align="center">
  <h1 align="center">🛡️ plyra-guard</h1>
  <p align="center">
    <em>Part of the <a href="https://plyra.dev">Plyra</a> agentic infrastructure suite.</em>
  </p>
  <p align="center">
    <strong>Production-grade middleware for securing, observing, and controlling actions taken by AI agents.</strong>
  </p>
  <p align="center">
    <a href="#"><img src="https://img.shields.io/pypi/v/plyra-guard?color=blue" alt="PyPI"></a>
    <a href="#"><img src="https://img.shields.io/pypi/pyversions/plyra-guard" alt="Python Version"></a>
    <a href="#"><img src="https://img.shields.io/badge/license-Apache--2.0-green" alt="License"></a>
    <a href="#"><img src="https://img.shields.io/badge/tests-193%20passing-brightgreen" alt="Tests"></a>
  </p>
</p>

```bash
pip install plyra-guard
```

Built by [Plyra](https://plyra.dev) — Infrastructure for Agentic AI.

---

## Why plyra-guard?

- **🔒 Every action passes through a security pipeline** — Intercept → Evaluate → Execute → Observe → Rollback. No unguarded tool calls.
- **🤖 Works with any AI framework** — LangChain, LlamaIndex, CrewAI, AutoGen, OpenAI, Anthropic, or plain Python callables.
- **🌐 Multi-agent native** — Trust ledgers, delegation tracking, cascade control, and cross-agent rollback built in from day one.

---

## Quick Install

```bash
pip install plyra-guard
```

With optional features:
```bash
pip install plyra-guard[sidecar]    # HTTP sidecar server
pip install plyra-guard[otel]       # OpenTelemetry export
pip install plyra-guard[all]        # Everything
```

---

## Quickstart

### 1. Basic Decorator

```python
from plyra_guard import ActionGuard, RiskLevel

guard = ActionGuard.default()

@guard.protect("file.delete", risk_level=RiskLevel.HIGH)
def delete_file(path: str) -> bool:
    import os
    os.remove(path)
    return True

# Every call is intercepted, evaluated, and audited
delete_file("/tmp/test.txt")
```

### 2. Namespace Import

```python
# Both import styles work:
from plyra_guard import ActionGuard      # direct
from plyra.guard import ActionGuard      # namespace
```

### 3. Multi-Agent Orchestration

```python
from plyra_guard import ActionGuard, TrustLevel

guard = ActionGuard.default()

# Register agents with trust levels
guard.register_agent("orchestrator", TrustLevel.ORCHESTRATOR)
guard.register_agent("email-agent", TrustLevel.SUB_AGENT)
guard.register_agent("code-agent", TrustLevel.PEER)

# Context manager sets active agent
with guard.set_task_context("task-001", "email-agent"):
    send_email("boss@company.com", "Report", "...")

# Roll back all actions in a task across all agents
guard.rollback_task("task-001")
```

### 4. Policy Configuration (YAML)

```yaml
# guard_config.yaml
version: "1.0"

policies:
  - name: "block_system_paths"
    action_types: ["file.delete", "file.write"]
    condition: "parameters.path.startswith('/etc')"
    verdict: BLOCK
    message: "System path access is forbidden"

  - name: "escalate_high_cost"
    action_types: ["*"]
    condition: "estimated_cost > 0.50"
    verdict: ESCALATE
    message: "Requires human approval"

agents:
  - id: "orchestrator"
    trust_level: 0.8
    can_delegate_to: ["worker-1", "worker-2"]
```

```python
guard = ActionGuard.from_config("guard_config.yaml")
```

---

## CLI

```bash
plyra-guard serve --config guard.yaml        # HTTP sidecar
plyra-guard inspect --config guard.yaml      # Pipeline visualization
plyra-guard explain --action file.delete     # Dry-run explanation
plyra-guard test-policy --condition "..."    # Interactive policy testing
plyra-guard version                          # Version info
```

---

## Supported Frameworks

`plyra-guard` natively configures transparent adapters handling tool executions across the most popular multi-agent frameworks. Depending on your framework's internal architecture, the recommended integration pattern differs:

| Framework | Recommended approach |
|-----------|----------------------|
| **LangChain** | `guard.wrap(tools)` |
| **LangGraph** | Custom `GuardedToolNode` (see [examples/langgraph_integration.py](examples/langgraph_integration.py)) |
| **AutoGen** | `guard.wrap([func])` + `register_function` |
| **CrewAI** | `guard.wrap(tools)` |
| **OpenAI / Anthropic** | `guard.wrap(tool_defs)` |
| **Generic Python** | `@guard.protect()` decorator |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        AI Agent / Framework                       │
│  (LangChain, LlamaIndex, CrewAI, AutoGen, OpenAI, Anthropic)    │
└─────────────────────────────┬────────────────────────────────────┘
                              │ tool call
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                      🛡️  plyra-guard                               │
│                                                                   │
│  ┌─────────┐  ┌──────────────────────────┐  ┌─────────────────┐ │
│  │ Adapter  │→│   Evaluation Pipeline     │→│ Execution Gate  │ │
│  │ Registry │  │                          │  │                 │ │
│  │          │  │ 1. Schema Validator      │  │ • Pre/post hooks│ │
│  │ • Lang-  │  │ 2. Policy Engine (YAML)  │  │ • Timeout mgmt  │ │
│  │   Chain  │  │ 3. Risk Scorer (0.0-1.0) │  │ • Error capture │ │
│  │ • OpenAI │  │ 4. Rate Limiter          │  │                 │ │
│  │ • Custom │  │ 5. Cost Estimator        │  └────────┬────────┘ │
│  └─────────┘  │ 6. Human Gate (optional)  │           │          │
│               │ 7. Custom evaluators...   │           │          │
│               └──────────────────────────┘           │          │
│                                                       │          │
│  ┌─────────────────┐  ┌───────────────┐  ┌──────────▼────────┐ │
│  │  Multi-Agent     │  │   Rollback    │  │  Observability    │ │
│  │                  │  │               │  │                   │ │
│  │ • Trust Ledger   │  │ • Snapshots   │  │ • Audit Log       │ │
│  │ • Instr. Chain   │  │ • File handler│  │ • OpenTelemetry   │ │
│  │ • Cascade Ctrl   │  │ • DB handler  │  │ • Datadog         │ │
│  │ • Global Budget  │  │ • HTTP comp.  │  │ • Webhooks        │ │
│  └─────────────────┘  └───────────────┘  └───────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## Features

### Evaluation Pipeline
Six built-in evaluators, fully pluggable:

| Evaluator | Purpose |
|-----------|---------|
| `SchemaValidator` | Validates ActionIntent structure |
| `PolicyEngine` | YAML policies with AST-compiled conditions |
| `RiskScorer` | Dynamic risk score (0.0-1.0) from 5 signals |
| `RateLimiter` | Per-agent, per-tool sliding window limits |
| `CostEstimator` | Token + API cost budget enforcement |
| `HumanGate` | Human-in-the-loop approval gate |

Add your own:
```python
from plyra_guard import BaseEvaluator, ActionIntent, EvaluatorResult, Verdict

class MyEvaluator(BaseEvaluator):
    @property
    def name(self) -> str:
        return "my_evaluator"

    def evaluate(self, intent: ActionIntent) -> EvaluatorResult:
        if "dangerous" in intent.parameters:
            return EvaluatorResult(verdict=Verdict.BLOCK, reason="Dangerous parameter")
        return EvaluatorResult(verdict=Verdict.ALLOW, reason="OK")

guard.pipeline.add(MyEvaluator(), position="after_risk_scorer")
```

### Multi-Agent Support
- **Trust Ledger** — Register agents with trust levels (HUMAN, ORCHESTRATOR, PEER, SUB_AGENT)
- **Instruction Chain** — Immutable provenance tracking across delegation hops
- **Cascade Controller** — Loop detection, depth limits, concurrent delegation caps
- **Global Budget** — Cross-agent cost aggregation with gaming detection

### Rollback System
- Automatic pre-execution state snapshots
- Built-in handlers for files, databases, and HTTP (compensation endpoints)
- Cross-agent `rollback_task()` undoes actions in reverse order

### HTTP Sidecar
Language-agnostic access via HTTP:
```bash
plyra-guard serve --config guard_config.yaml --port 8080

curl -X POST http://localhost:8080/evaluate \
  -H "Content-Type: application/json" \
  -d '{"action_type": "file.read", "parameters": {"path": "/tmp/test"}, "agent_id": "my-agent"}'
```

---

## Documentation

| Guide | Description |
|-------|-------------|
| [Quickstart](docs/quickstart.md) | Get started in 5 minutes |
| [Architecture](docs/architecture.md) | How plyra-guard works internally |
| [Policy Reference](docs/policy_reference.md) | YAML policy syntax and built-in functions |
| [Multi-Agent Guide](docs/multiagent_guide.md) | Trust, delegation, and cascading |
| [Rollback Guide](docs/rollback_guide.md) | Snapshot and rollback system |
| [Adapters](docs/adapters.md) | Framework integration details |
| [API Reference](docs/api_reference.md) | Full public API documentation |

---

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

```bash
git clone https://github.com/plyra/plyra-guard.git
cd plyra-guard
pip install -e ".[dev,sidecar]"
pytest tests/ -v
```

---

## License

Apache-2.0 License — see [LICENSE](LICENSE) for details.

---

plyra-guard is part of the Plyra suite.
Explore the full stack at [plyra.dev](https://plyra.dev).

| Library       | Purpose                    | Status    |
|---------------|----------------------------|-----------|
| plyra-guard   | Action safety middleware   | ✅ stable |
| plyra-memory  | Tiered agent memory        | 🔜 soon  |
| plyra-trace   | Observability & debugging  | 🔜 soon  |
| plyra-budget  | Cost optimization          | 🔜 soon  |
| plyra-mesh    | Multi-agent communication  | 🔜 soon  |
