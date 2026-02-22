# Installation

## Requirements

- Python 3.11, 3.12, or 3.13
- pip or uv

## Basic Install

```bash
pip install plyra-guard
```

Or with [uv](https://github.com/astral-sh/uv) (recommended):

```bash
uv add plyra-guard
```

## Optional Extras

Plyra Guard is modular. Install only what you need:

```bash
# Dashboard UI + sidecar API server
pip install "plyra-guard[sidecar]"

# OpenTelemetry exporter
pip install "plyra-guard[otel]"

# Datadog exporter
pip install "plyra-guard[datadog]"

# S3 snapshot storage
pip install "plyra-guard[storage]"

# Everything
pip install "plyra-guard[all]"
```

## Verify Install

```python
import plyra_guard
print(plyra_guard.__version__)
```

## Development Install

```bash
git clone https://github.com/plyraAI/plyra-guard
cd plyra-guard
uv sync --all-extras
uv run pytest
```

!!! tip
    Use a virtual environment to keep your project dependencies isolated.
    `uv` handles this automatically.
