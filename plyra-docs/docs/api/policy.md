# Policy & Rule

## Policy

```python
Policy(
    rules: list[Rule],
    name: str = "default",
    default_action: Literal["allow", "block"] = "block",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `rules` | `list[Rule]` | required | Ordered list of rules. First match wins. |
| `name` | `str` | `"default"` | Policy name (appears in logs) |
| `default_action` | `str` | `"block"` | Action when no rule matches |

### Methods

```python
policy.evaluate(intent: str) -> EvaluationResult
```

Evaluate an intent string and return the result.

```python
policy.add_rule(rule: Rule, index: int | None = None) -> None
```

Add a rule at a given position (default: append to end).

---

## Rule

```python
Rule(
    pattern: str,
    action: Literal["allow", "block", "escalate"],
    reason: str = "",
    name: str | None = None,
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pattern` | `str` | required | Python regex matched against intent |
| `action` | `str` | required | `"allow"`, `"block"`, or `"escalate"` |
| `reason` | `str` | `""` | Human-readable explanation (logged) |
| `name` | `str` | auto | Rule identifier for logs |

### Pattern Matching

Patterns use `re.search()` — the pattern can match anywhere in the intent string unless anchored with `^` or `$`.

```python
# Matches /etc/anything
Rule(pattern=r"^/etc/", action="block")

# Matches any .env file anywhere in the path
Rule(pattern=r"\.env$", action="block")

# Matches exact string "DROP TABLE"
Rule(pattern=r"DROP TABLE", action="block")
```

### Escalation

`escalate` pauses the action and waits for human approval. Requires an escalation handler to be configured:

```python
async def my_approval_handler(action: ActionRecord) -> bool:
    # Return True to approve, False to deny
    response = await send_slack_approval(action)
    return response == "approve"

guard = ActionGuard(
    policy=policy,
    escalation_handler=my_approval_handler,
)
```
