# Quickstart

Get Plyra Guard running in under 5 minutes.

## 1. Install

```bash
pip install plyra-guard
```

## 2. Wrap Your First Tool

```python
from plyra_guard import ActionGuard

guard = ActionGuard()

@guard.wrap
def read_file(path: str) -> str:
    with open(path) as f:
        return f.read()

@guard.wrap
def delete_file(path: str) -> str:
    import os
    os.remove(path)
    return f"Deleted {path}"

# This works — /tmp is allowed
content = read_file("/tmp/data.txt")

# This is blocked — /etc is protected
delete_file("/etc/passwd")  # raises PolicyViolationError
```

## 3. Check What Happened

```python
# Print the last 10 actions
for action in guard.history(limit=10):
    print(action.intent, action.outcome, action.latency_ms)
```

## 4. Add a Custom Policy

```python
from plyra_guard import ActionGuard, Policy, Rule

policy = Policy(
    rules=[
        Rule(pattern=r"\.env$", action="block", reason="No .env access"),
        Rule(pattern=r"^/prod/", action="block", reason="Production is read-only"),
        Rule(pattern=r"^/tmp/", action="allow"),
    ]
)

guard = ActionGuard(policy=policy)
```

Or load from YAML:

```yaml title="policy.yaml"
rules:
  - pattern: "\.env$"
    action: block
    reason: "No .env access"
  - pattern: "^/prod/"
    action: block
    reason: "Production is read-only"
  - pattern: "^/tmp/"
    action: allow
```

```python
guard = ActionGuard.from_config("policy.yaml")
```

## 5. Launch the Dashboard

```bash
pip install "plyra-guard[sidecar]"
plyra-guard serve
```

Open [http://localhost:8765](http://localhost:8765) to see your real-time action feed.

## Next Steps

- [Core Concepts](concepts.md) — understand how evaluation works
- [Policy Configuration](../guides/policy-config.md) — full policy reference
- [Framework Integrations](../integrations/index.md) — LangGraph, AutoGen, CrewAI
