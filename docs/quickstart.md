# Quickstart Guide

Get started with ActionGuard in under 5 minutes.

## Installation

```bash
pip install actionguard
```

## Your First Guarded Function

```python
from actionguard import ActionGuard, RiskLevel

# Create a guard with sensible defaults
guard = ActionGuard.default()

# Protect a function with the decorator
@guard.protect("file.delete", risk_level=RiskLevel.HIGH)
def delete_file(path: str) -> bool:
    import os
    os.remove(path)
    return True

# Call it normally — ActionGuard intercepts, evaluates, and audits
delete_file("/tmp/test.txt")
```

## Adding Policies

Create a `guard_config.yaml`:

```yaml
version: "1.0"

policies:
  - name: "block_system_paths"
    action_types: ["file.delete", "file.write"]
    condition: "parameters.path.startswith('/etc')"
    verdict: BLOCK
    message: "System path access is forbidden"
```

Load it:

```python
guard = ActionGuard.from_config("guard_config.yaml")
```

## Wrapping Framework Tools

```python
# Works with any framework
tools = [my_langchain_tool, my_openai_tool, my_function]
wrapped_tools = guard.wrap(tools)
# Use wrapped_tools exactly like the originals
```

## Checking the Audit Log

```python
for entry in guard.get_audit_log():
    print(f"[{entry.verdict.value}] {entry.action_type} by {entry.agent_id}")
```

## Next Steps

- [Architecture Guide](architecture.md) — understand the pipeline
- [Policy Reference](policy_reference.md) — master YAML policies
- [Multi-Agent Guide](multiagent_guide.md) — set up trust and delegation
