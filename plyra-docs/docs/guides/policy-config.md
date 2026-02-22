# Policy Configuration

Policies are the core of Plyra Guard. They define what your agents are and aren't allowed to do.

## YAML Configuration

The recommended way to define policies is in a YAML file:

```yaml title="policy.yaml"
version: "1"
name: "production"
default_action: block   # what to do if no rule matches (default: block)

rules:
  # Filesystem
  - pattern: "^/etc/"
    action: block
    reason: "System config is off-limits"

  - pattern: "\\.env$"
    action: block
    reason: "No .env file access"

  - pattern: "^/tmp/"
    action: allow
    reason: "Temp directory is safe"

  # Network
  - pattern: "https://internal\\.corp"
    action: block
    reason: "Internal network access not permitted"

  # Destructive operations
  - pattern: "rm -rf"
    action: block
    reason: "No recursive deletes"

  - pattern: "DROP TABLE"
    action: escalate
    reason: "Schema changes require human approval"
```

Load it with:

```python
guard = ActionGuard.from_config("policy.yaml")
```

## Python Configuration

For dynamic policies or when you need programmatic control:

```python
from plyra_guard import ActionGuard, Policy, Rule

policy = Policy(
    name="production",
    default_action="block",
    rules=[
        Rule(
            pattern=r"^/etc/",
            action="block",
            reason="System config is off-limits"
        ),
        Rule(
            pattern=r"^/tmp/",
            action="allow",
            reason="Temp directory is safe"
        ),
    ]
)

guard = ActionGuard(policy=policy)
```

## Rule Matching

Rules are evaluated **in order** — the first match wins.

```python
rules=[
    Rule(pattern=r"^/tmp/reports/", action="allow"),   # more specific first
    Rule(pattern=r"^/tmp/",         action="block"),   # catches everything else in /tmp
]
```

!!! warning "Order matters"
    Put more specific rules before more general ones. A catch-all `.*` block rule at the top would match everything.

## Pattern Syntax

Patterns are Python regular expressions matched against the **intent string**.

| Pattern | Matches |
|---------|---------|
| `^/etc/` | Any path starting with `/etc/` |
| `\.env$` | Any string ending with `.env` |
| `DROP TABLE` | Any intent containing `DROP TABLE` |
| `^(rm\|delete)\s` | Intent starting with `rm` or `delete` |

## Actions

| Action | Behaviour |
|--------|-----------|
| `allow` | Tool executes normally |
| `block` | Tool is not called, `PolicyViolationError` raised immediately |
| `escalate` | Tool is paused, human approval required (async workflows) |

## Default Action

If no rule matches, the `default_action` is applied. It defaults to `block` — fail closed.

```yaml
default_action: allow   # permissive (not recommended for production)
default_action: block   # restrictive (recommended)
```

## Environment-Specific Policies

```python
import os
from plyra_guard import ActionGuard

config_file = f"policy.{os.getenv('ENV', 'development')}.yaml"
guard = ActionGuard.from_config(config_file)
```

## Testing Your Policy

```python
# Dry-run evaluation without executing tools
result = guard.evaluate("rm -rf /var/log")
print(result.outcome)    # BLOCK
print(result.reason)     # "No recursive deletes"
print(result.rule_name)  # the rule that matched
```
