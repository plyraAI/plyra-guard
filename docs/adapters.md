# Adapters Guide

## Overview

Adapters translate framework-specific tool objects into ActionGuard's universal `ActionIntent` format.

## Supported Frameworks

| Framework | Adapter | Auto-detected |
|-----------|---------|---------------|
| LangChain | `LangChainAdapter` | ✅ BaseTool, StructuredTool |
| LlamaIndex | `LlamaIndexAdapter` | ✅ FunctionTool, QueryEngineTool |
| CrewAI | `CrewAIAdapter` | ✅ BaseTool |
| AutoGen | `AutoGenAdapter` | ✅ Registered functions |
| OpenAI | `OpenAIAdapter` | ✅ Function call dicts |
| Anthropic | `AnthropicAdapter` | ✅ tool_use dicts |
| Generic | `GenericAdapter` | ✅ Any Python callable |

## Usage

```python
# Wrap any mix of tools — auto-detected
wrapped = guard.wrap([
    langchain_tool,
    openai_tool_dict,
    my_python_function,
])
```

## Custom Adapters

```python
from actionguard import BaseAdapter, ActionIntent

class MyFrameworkAdapter(BaseAdapter):
    @property
    def framework_name(self) -> str:
        return "my_framework"

    def can_handle(self, tool):
        return isinstance(tool, MyFrameworkTool)

    def to_intent(self, tool, inputs, agent_id):
        return ActionIntent(
            action_type=f"my_framework.{tool.name}",
            tool_name=tool.name,
            parameters=inputs,
            agent_id=agent_id,
        )

    def wrap(self, tool, guard):
        # Return a framework-native tool with guarded execution
        ...

# Register with priority
guard._adapter_registry.register(MyFrameworkAdapter(), priority=0)
```
