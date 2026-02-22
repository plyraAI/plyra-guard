<div align="center">

<img src="https://plyraai.github.io/plyra-guard/assets/logo.png" width="72" height="72" alt="Plyra" />

# plyra-guard

**Production-grade action middleware for agentic AI**

[![PyPI](https://img.shields.io/pypi/v/plyra-guard?color=2dd4bf&labelColor=0d1117&label=pypi)](https://pypi.org/project/plyra-guard)
[![Python](https://img.shields.io/pypi/pyversions/plyra-guard?color=2dd4bf&labelColor=0d1117)](https://pypi.org/project/plyra-guard)
[![Tests](https://img.shields.io/github/actions/workflow/status/plyraAI/plyra-guard/ci.yml?color=2dd4bf&labelColor=0d1117&label=tests)](https://github.com/plyraAI/plyra-guard/actions)
[![License](https://img.shields.io/badge/license-Apache%202.0-2dd4bf?labelColor=0d1117)](LICENSE)
[![Downloads](https://img.shields.io/pypi/dm/plyra-guard?color=2dd4bf&labelColor=0d1117)](https://pypi.org/project/plyra-guard)

[Documentation](https://plyraai.github.io/plyra-guard) · [PyPI](https://pypi.org/project/plyra-guard) · [plyra.ai](https://plyraai.github.io)

</div>

---

AI agents are being deployed to take real-world actions — deleting files, calling APIs, sending emails. **There is no standard safety layer between the LLM's decision and execution.**

`plyra-guard` is that layer. It intercepts every tool call your agent makes, evaluates it against your policy, and blocks, logs, or escalates — before anything irreversible happens.

```python
from plyra_guard import ActionGuard

guard = ActionGuard()

@guard.wrap
def delete_file(path: str) -> str:
    import os
    os.remove(path)
    return f"Deleted {path}"

delete_file("/tmp/report.txt")   # ✓  ALLOW  0.3ms
delete_file("/etc/passwd")       # ✗  BLOCK  "System config is off-limits"
```

## Why plyra-guard?

- **Framework agnostic** — one-line wrap for LangGraph, AutoGen, CrewAI, LangChain, OpenAI, Anthropic, or plain Python
- **Policy as code** — rules live in your repo, reviewed in PRs, tested in CI
- **Zero latency budget** — evaluation happens in-process, no network hop, sub-2ms overhead
- **Full audit log** — every action logged (allowed and blocked), ships to OTEL, Datadog, or your own sink
- **Built-in dashboard** — real-time action feed, policy hit rates, session replay at `localhost:8765`

## Installation

```bash
pip install plyra-guard
```

Optional extras:

```bash
pip install "plyra-guard[sidecar]"   # dashboard + REST API
pip install "plyra-guard[otel]"      # OpenTelemetry exporter
pip install "plyra-guard[datadog]"   # Datadog exporter
pip install "plyra-guard[all]"       # everything
```

## Quickstart

### 1. Wrap your tools

```python
from plyra_guard import ActionGuard

guard = ActionGuard()

@guard.wrap
def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()

@guard.wrap
def write_file(path: str, content: str) -> str:
    with open(path, "w") as f:
        f.write(content)
    return f"Written to {path}"
```

### 2. Define a policy

```yaml
# policy.yaml
version: "1"
default_action: block

rules:
  - pattern: "\.env$"
    action: block
    reason: "No .env access"

  - pattern: "^/etc/"
    action: block
    reason: "System config is off-limits"

  - pattern: "^/tmp/"
    action: allow

  - pattern: "DROP TABLE"
    action: escalate
    reason: "Schema changes require human approval"
```

```python
guard = ActionGuard.from_config("policy.yaml")
```

### 3. Query what happened

```python
for action in guard.history(limit=20, outcome="BLOCK"):
    print(f"{action.tool_name} | {action.intent} | {action.latency_ms}ms")
```

### 4. Launch the dashboard

```bash
pip install "plyra-guard[sidecar]"
plyra-guard serve
# → http://localhost:8765
```

## Framework Integrations

### LangGraph

LangGraph's `ToolNode` uses internal state tracking that conflicts with transparent wrapping. Use a custom guarded node instead — this is the recommended pattern:

```python
from langchain_core.messages import ToolMessage
from plyra_guard import ActionGuard
from plyra_guard.exceptions import PolicyViolationError

guard = ActionGuard()
TOOLS = {"read_file": read_file_tool, "delete_file": delete_file_tool}

def guarded_tool_node(state):
    messages = []
    for tool_call in state["messages"][-1].tool_calls:
        intent = f"{tool_call['name']} {' '.join(str(v) for v in tool_call['args'].values())}"
        try:
            result = guard.evaluate(intent)
            if result.outcome == "BLOCK":
                content = f"[BLOCKED] {result.reason}"
            else:
                content = TOOLS[tool_call["name"]].invoke(tool_call["args"])
        except Exception as e:
            content = f"[ERROR] {e}"
        messages.append(ToolMessage(content=str(content), tool_call_id=tool_call["id"]))
    return {"messages": messages}
```

See [`examples/langgraph_integration.py`](examples/langgraph_integration.py) for a complete working graph.

### AutoGen

```python
import autogen
from plyra_guard import ActionGuard

guard = ActionGuard()
safe_tools = guard.wrap([read_file, delete_file])

user_proxy = autogen.UserProxyAgent("user_proxy", human_input_mode="NEVER")
for tool in safe_tools:
    user_proxy.register_function(function_map={tool.__name__: tool})
```

Blocked calls return an error string into the conversation — the agent sees it and can course-correct. No crash, no infinite loop.

### CrewAI

```python
from crewai_tools import tool
from plyra_guard import ActionGuard

guard = ActionGuard()

@tool("Write Report")
def write_report(path: str, content: str) -> str:
    """Write a report to disk."""
    with open(path, "w") as f:
        f.write(content)
    return f"Written to {path}"

safe_tools = guard.wrap([write_report])

agent = Agent(role="Analyst", tools=safe_tools, ...)
```

Blocked calls raise `ActionGuardExecutionError`, which CrewAI's task loop catches natively.

### LangChain

```python
from plyra_guard import ActionGuard

guard = ActionGuard()
safe_tools = guard.wrap(tools)  # drop-in replacement

agent = create_react_agent(llm, safe_tools, prompt)
```

### Plain Python / any framework

```python
# Decorator
@guard.wrap
def my_function(arg: str) -> str: ...

# Direct wrap
safe_fn = guard.wrap(some_function)

# Wrap a list
safe_tools = guard.wrap([tool1, tool2, tool3])
```

| Framework | Approach |
|-----------|----------|
| LangChain | `guard.wrap(tools)` |
| LangGraph | Custom `guarded_tool_node` (see example) |
| AutoGen | `guard.wrap([fn])` + `register_function` |
| CrewAI | `guard.wrap(tools)` |
| OpenAI | `guard.wrap(tool_defs)` |
| Anthropic | `guard.wrap(tool_defs)` |
| Plain Python | `@guard.wrap` decorator |

## Policy Reference

Rules are evaluated in order. First match wins.

```python
from plyra_guard import Policy, Rule

policy = Policy(
    default_action="block",   # fail closed by default
    rules=[
        Rule(pattern=r"^/etc/",    action="block",    reason="System config"),
        Rule(pattern=r"\.env$",    action="block",    reason="No .env access"),
        Rule(pattern=r"^/tmp/",    action="allow"),
        Rule(pattern=r"DROP TABLE",action="escalate", reason="Needs human approval"),
    ]
)
```

| Action | Behaviour |
|--------|-----------|
| `allow` | Tool executes normally |
| `block` | Tool not called, `PolicyViolationError` raised |
| `escalate` | Paused pending human approval (async) |

Test a policy without running anything:

```python
result = guard.evaluate("rm -rf /var/log")
print(result.outcome)    # BLOCK
print(result.reason)     # "No recursive deletes"
print(result.latency_ms) # 0.4
```

## Observability

```python
from plyra_guard import ActionGuard
from plyra_guard.exporters import OtelExporter, SidecarExporter

guard = ActionGuard(exporters=[
    OtelExporter(endpoint="http://localhost:4317"),
    SidecarExporter(),   # streams to dashboard
])
```

> **Note:** `StdoutExporter` is enabled by default. To disable it in production:
> set `exporters=[]` or configure `observability.exporters: []` in your YAML config.

## Configuration Notes

- **Snapshot DB:** Action history is written to `~/.plyra/snapshots.db` on first import. Set `PLYRA_SNAPSHOT_PATH` to change the location.
- **Dashboard CORS:** The sidecar defaults to `allow_origins=["*"]` — fine for localhost, lock it down if exposed beyond localhost in production.

## Development

```bash
git clone https://github.com/plyraAI/plyra-guard
cd plyra-guard
uv sync --all-extras
uv run pytest                    # 217 tests
uv run ruff check .              # lint
uv run mypy plyra_guard/         # types
```

## Project Status

`plyra-guard` is in **beta** (v0.1.x). The API is stable but we may make minor breaking changes before v1.0 with appropriate deprecation notices.

**Coming soon:** [`plyra-memory`](https://plyraai.github.io) — persistent episodic and semantic memory for agents. Watch the repo or follow [@plyraAI](https://twitter.com/plyraAI) for updates.

## Contributing

Issues and PRs are welcome. Please open an issue before starting significant work so we can discuss the approach.

- Run `ruff format` before committing
- Add tests for new behaviour
- Update `CHANGELOG.md`

## License

Apache 2.0 — see [LICENSE](LICENSE).

---

<div align="center">

Built by [Plyra](https://plyraai.github.io) · Infrastructure for agentic AI

</div>
