# ActionGuard

The central class. Create one per application (or one per agent for separate policies).

## Constructor

```python
ActionGuard(
    policy: Policy | None = None,
    exporters: list[Exporter] | None = None,
    snapshot_path: str | None = "~/.plyra/snapshots.db",
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `policy` | `Policy` | built-in defaults | Policy to evaluate actions against |
| `exporters` | `list[Exporter]` | `[StdoutExporter()]` | Where to send action logs |
| `snapshot_path` | `str \| None` | `~/.plyra/snapshots.db` | SQLite file for persistent history. `None` to disable. |

## Class Methods

### `from_config`

```python
@classmethod
def from_config(cls, path: str) -> ActionGuard
```

Load a guard from a YAML policy file.

```python
guard = ActionGuard.from_config("policy.yaml")
```

## Instance Methods

### `wrap`

```python
def wrap(
    fn: Callable | list[Callable],
    *,
    intent_fn: Callable | None = None,
) -> Callable | list[Callable]
```

Wrap one or more callables with policy evaluation. Can be used as a decorator or called directly.

```python
# Decorator
@guard.wrap
def my_tool(path: str) -> str: ...

# Direct call
safe_tools = guard.wrap([tool1, tool2, tool3])

# Custom intent extraction
@guard.wrap(intent_fn=lambda args, kwargs: kwargs.get("path", ""))
def delete_file(path: str) -> None: ...
```

### `evaluate`

```python
def evaluate(intent: str) -> EvaluationResult
```

Evaluate an intent string against the policy without executing any tool. Useful for testing policies or pre-checking before expensive operations.

```python
result = guard.evaluate("rm -rf /var/log")
print(result.outcome)    # "BLOCK"
print(result.reason)     # "No recursive deletes"
print(result.rule_name)  # "no-rm-rf"
print(result.latency_ms) # 0.3
```

### `history`

```python
def history(
    limit: int = 100,
    outcome: str | None = None,
    tool_name: str | None = None,
    since: datetime | None = None,
) -> list[ActionRecord]
```

Query the action log.

```python
# Last 50 blocks
blocks = guard.history(limit=50, outcome="BLOCK")

# All delete_file calls today
from datetime import datetime, timedelta
today = datetime.now() - timedelta(hours=24)
deletes = guard.history(tool_name="delete_file", since=today)
```

## `EvaluationResult`

| Field | Type | Description |
|-------|------|-------------|
| `outcome` | `str` | `"ALLOW"`, `"BLOCK"`, or `"ESCALATE"` |
| `reason` | `str` | Human-readable explanation |
| `rule_name` | `str \| None` | Name of the matching rule |
| `latency_ms` | `float` | Evaluation time in milliseconds |

## `ActionRecord`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | UUID |
| `tool_name` | `str` | Name of the wrapped function |
| `intent` | `str` | Intent string evaluated |
| `outcome` | `str` | `"ALLOW"`, `"BLOCK"`, `"ESCALATE"`, `"ERROR"` |
| `reason` | `str` | Why this outcome was chosen |
| `latency_ms` | `float` | End-to-end time including tool execution |
| `timestamp` | `datetime` | When the action occurred |
| `args` | `dict` | Full argument payload |
| `result` | `Any` | Return value (None if blocked) |
| `error` | `str \| None` | Exception message if outcome is ERROR |
