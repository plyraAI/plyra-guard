# Policy Reference

## Overview

Policies are declared in YAML and compiled into an AST at startup for near-zero evaluation latency.

## Policy Structure

```yaml
policies:
  - name: "unique_policy_name"
    action_types: ["file.delete", "http.*"]  # glob patterns
    condition: "parameters.path.startswith('/etc')"
    verdict: BLOCK  # BLOCK, ESCALATE, DEFER, WARN, ALLOW_OVERRIDE
    message: "Human-readable explanation"
    escalate_to: human  # optional
```

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique policy identifier |
| `action_types` | list[string] | Yes | Glob patterns for matching |
| `condition` | string | Yes | Python-like expression |
| `verdict` | string | Yes | What to do when triggered |
| `message` | string | No | Explanation shown to caller |
| `escalate_to` | string | No | Who to escalate to |

## Condition Expressions

### Available Variables

| Variable | Description |
|----------|-------------|
| `parameters` | The action's parameter dict (dot-notation access) |
| `estimated_cost` | Estimated cost in USD |
| `risk_level` | Risk level string |
| `agent.trust_level` | Caller's trust score |
| `agent.action_count` | Actions by this agent in current run |
| `task.estimated_cost` | Total task cost estimate |

### Operators

- Comparison: `>`, `<`, `>=`, `<=`, `==`, `!=`
- Logical: `and`, `or`, `not`
- String: `.startswith()`, `.endswith()`, `.contains()`

### Built-in Functions

| Function | Description |
|----------|-------------|
| `contains_pii(parameters)` | Detects SSN, email, CC, phone patterns |
| `is_sensitive_path(path)` | Checks against system paths |

## Examples

```yaml
# Block system path access
- name: "block_system_paths"
  action_types: ["file.*"]
  condition: "parameters.path.startswith('/etc')"
  verdict: BLOCK

# Escalate expensive actions
- name: "escalate_costly"
  action_types: ["*"]
  condition: "estimated_cost > 1.00"
  verdict: ESCALATE

# Block PII in outbound requests
- name: "pii_guard"
  action_types: ["http.post", "email.send"]
  condition: "contains_pii(parameters)"
  verdict: BLOCK
```
