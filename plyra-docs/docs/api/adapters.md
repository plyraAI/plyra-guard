# Adapters & Exporters

## Exporters

Exporters receive every `ActionRecord` after evaluation and route it to your observability stack.

### StdoutExporter (default)

Logs to stdout in a structured format. Active by default — useful during development.

```python
from plyra_guard.exporters import StdoutExporter

guard = ActionGuard(exporters=[StdoutExporter(level="INFO")])
```

Disable by passing an empty list:

```python
guard = ActionGuard(exporters=[])
```

### OtelExporter

Ships actions as OpenTelemetry spans.

```bash
pip install "plyra-guard[otel]"
```

```python
from plyra_guard.exporters import OtelExporter

guard = ActionGuard(exporters=[
    OtelExporter(endpoint="http://localhost:4317")
])
```

### DatadogExporter

Ships actions as Datadog custom events.

```bash
pip install "plyra-guard[datadog]"
```

```python
from plyra_guard.exporters import DatadogExporter

guard = ActionGuard(exporters=[
    DatadogExporter(service="my-agent", env="production")
])
```

### SidecarExporter

Streams actions to the local dashboard sidecar.

```bash
pip install "plyra-guard[sidecar]"
```

```python
from plyra_guard.exporters import SidecarExporter

guard = ActionGuard(exporters=[
    SidecarExporter(url="http://localhost:8765")
])
```

### Multiple Exporters

```python
guard = ActionGuard(exporters=[
    StdoutExporter(),
    OtelExporter(endpoint="http://otel-collector:4317"),
    SidecarExporter(),
])
```

---

## Custom Exporter

Implement the `Exporter` protocol:

```python
from plyra_guard.exporters import Exporter
from plyra_guard.models import ActionRecord

class MyExporter(Exporter):
    def export(self, action: ActionRecord) -> None:
        # your logic here
        my_db.insert(action.model_dump())
```

---

## Exceptions

### `PolicyViolationError`

Raised when a wrapped tool call is blocked.

```python
from plyra_guard.exceptions import PolicyViolationError

try:
    delete_file("/etc/passwd")
except PolicyViolationError as e:
    print(e.reason)    # "System config is off-limits"
    print(e.rule_name) # "protect-system"
    print(e.intent)    # "/etc/passwd"
```

### `ActionGuardExecutionError`

Raised in CrewAI context (subclass of `PolicyViolationError`). Same fields.
