# Framework Integrations

Plyra Guard works with every major agentic framework. Pick yours:

<div class="feature-grid" markdown>

<div class="feature-card" markdown>
<div class="icon">🦜</div>
<h3><a href="langgraph/">LangGraph</a></h3>
<p>Custom tool node pattern. Works with StateGraph and any graph topology.</p>
</div>

<div class="feature-card" markdown>
<div class="icon">🤖</div>
<h3><a href="autogen/">AutoGen</a></h3>
<p>Wrap registered functions on UserProxyAgent.</p>
</div>

<div class="feature-card" markdown>
<div class="icon">⚓</div>
<h3><a href="crewai/">CrewAI</a></h3>
<p>Wrap @tool definitions. BlockedActions surface as CrewAI errors.</p>
</div>

</div>

## General Pattern

For any framework not listed, the general pattern is:

```python
from plyra_guard import ActionGuard

guard = ActionGuard()

# Option A — decorator
@guard.wrap
def my_tool(arg: str) -> str:
    ...

# Option B — wrap a list of tools
safe_tools = guard.wrap([tool1, tool2, tool3])

# Option C — wrap a callable
safe_fn = guard.wrap(some_function)
```

The wrapped version is a drop-in replacement — same signature, same return type, raises `PolicyViolationError` on block.
