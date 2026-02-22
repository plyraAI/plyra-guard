# Dashboard & Sidecar

Plyra Guard includes a built-in web dashboard and REST API sidecar for real-time monitoring.

## Install

```bash
pip install "plyra-guard[sidecar]"
```

## Start the Dashboard

```bash
plyra-guard serve
```

Or with custom options:

```bash
plyra-guard serve --host 0.0.0.0 --port 8765 --reload
```

Open [http://localhost:8765](http://localhost:8765) in your browser.

## What You'll See

### Action Feed

Real-time stream of every tool call your agents make:

- Tool name and intent string
- Outcome: `ALLOW` / `BLOCK` / `ESCALATE`
- Latency in milliseconds
- Which policy rule triggered
- Full argument payload (expandable)

### Policy Hit Rates

Bar chart showing which rules are firing most frequently. Useful for auditing overly broad or permissive rules.

### Session Replay

Replay any agent session from your snapshot history. See the exact sequence of tool calls, decisions, and results.

## Sidecar REST API

The sidecar exposes a REST API alongside the dashboard:

```
GET  /api/actions          — list recent actions
GET  /api/actions/{id}     — single action detail
GET  /api/stats            — aggregate stats
POST /api/policy/evaluate  — evaluate an intent string
GET  /api/health           — health check
```

### Example

```bash
# Check what your agent has been doing
curl http://localhost:8765/api/actions?limit=20&outcome=BLOCK

# Evaluate an intent before running
curl -X POST http://localhost:8765/api/policy/evaluate \
  -H "Content-Type: application/json" \
  -d '{"intent": "rm -rf /var/log"}'
```

## Connecting Your Guard to the Sidecar

```python
from plyra_guard import ActionGuard
from plyra_guard.exporters import SidecarExporter

guard = ActionGuard(
    exporters=[SidecarExporter(url="http://localhost:8765")]
)
```

Actions are streamed to the sidecar asynchronously — no latency impact on your agent.

## Production Considerations

!!! warning "CORS"
    The default sidecar allows all origins (`*`). In production, bind to localhost only or add authentication.

!!! tip "Snapshot database"
    Action history is stored in `~/.plyra/snapshots.db` by default. On a server, set `PLYRA_SNAPSHOT_PATH` to a persistent volume.

```bash
export PLYRA_SNAPSHOT_PATH=/data/plyra/snapshots.db
plyra-guard serve
```
