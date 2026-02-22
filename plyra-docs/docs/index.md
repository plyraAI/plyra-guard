# Plyra Guard

<div class="plyra-hero" markdown>

<div class="plyra-hero-title">Plyra Guard</div>

**Production-grade action middleware for agentic AI**

<p class="tagline">
Stop your agents before they do something irreversible.
Plyra Guard intercepts every tool call, evaluates it against your policy,
and blocks, logs, or escalates — in under 2ms.
</p>

<div class="badge-strip">

[![PyPI](https://img.shields.io/pypi/v/plyra-guard?color=2dd4bf&labelColor=0d1117)](https://pypi.org/project/plyra-guard)
[![Python](https://img.shields.io/pypi/pyversions/plyra-guard?color=2dd4bf&labelColor=0d1117)](https://pypi.org/project/plyra-guard)
[![License](https://img.shields.io/badge/license-Apache%202.0-2dd4bf?labelColor=0d1117)](https://github.com/plyraAI/plyra-guard/blob/main/LICENSE)
[![Tests](https://img.shields.io/github/actions/workflow/status/plyraAI/plyra-guard/ci.yml?color=2dd4bf&labelColor=0d1117&label=tests)](https://github.com/plyraAI/plyra-guard/actions)

</div>

[Get Started](getting-started/quickstart.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/plyraAI/plyra-guard){ .md-button }

</div>

## Why Plyra Guard?

LLM agents fail in the same ways: they delete files they shouldn't, call APIs with wrong credentials, exfiltrate data, or loop forever. These aren't model problems — they're **infrastructure problems**. Plyra Guard is the missing safety layer.

<div class="feature-grid" markdown>

<div class="feature-card" markdown>
<div class="icon">⚡</div>
<h3>Framework Agnostic</h3>
<p>One-line wrap for LangChain, LangGraph, AutoGen, CrewAI, OpenAI, Anthropic, or any Python function.</p>
</div>

<div class="feature-card" markdown>
<div class="icon">🛡️</div>
<h3>Policy as Code</h3>
<p>Define allow/block rules in YAML or Python. Regex, semantic, and custom evaluators supported.</p>
</div>

<div class="feature-card" markdown>
<div class="icon">📊</div>
<h3>Built-in Dashboard</h3>
<p>Real-time action feed, policy hit rates, agent session replay — all in a local web UI.</p>
</div>

<div class="feature-card" markdown>
<div class="icon">🔍</div>
<h3>Full Observability</h3>
<p>OpenTelemetry, Datadog, and stdout exporters. Every action logged with intent, outcome, and latency.</p>
</div>

</div>

## 60-Second Install

```bash
pip install plyra-guard
```

```python
from plyra_guard import ActionGuard

guard = ActionGuard()

@guard.wrap
def delete_file(path: str) -> str:
    import os
    os.remove(path)
    return f"Deleted {path}"

# Safe call — allowed
delete_file("/tmp/report.txt")

# Blocked by default policy
delete_file("/etc/passwd")  # → PolicyViolationError
```

## Framework Support

| Framework | Status | Pattern |
|-----------|--------|---------|
| LangChain | ✅ | `guard.wrap(tools)` |
| LangGraph | ✅ | Custom tool node |
| AutoGen | ✅ | `guard.wrap([func])` |
| CrewAI | ✅ | `guard.wrap(tools)` |
| OpenAI | ✅ | Function call interceptor |
| Anthropic | ✅ | Tool use interceptor |
| Plain Python | ✅ | `@guard.wrap` decorator |
