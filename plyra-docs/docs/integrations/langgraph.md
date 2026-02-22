# LangGraph Integration

LangGraph's `ToolNode` uses internal state tracking that conflicts with transparent wrapping. The recommended pattern is a **custom guarded tool node**.

## Why Custom Node?

LangGraph's `ToolNode` directly invokes tools and manages `ToolMessage` state internally. Wrapping tools before passing them to `ToolNode` works for simple cases, but breaks message correlation in complex graphs. A custom node gives you full control.

## Guarded Tool Node Pattern

```python
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, END
from plyra_guard import ActionGuard
from plyra_guard.exceptions import PolicyViolationError

guard = ActionGuard()

# Define your tools normally
@tool
def read_file(path: str) -> str:
    """Read a file from disk."""
    with open(path) as f:
        return f.read()

@tool
def delete_file(path: str) -> str:
    """Delete a file from disk."""
    import os
    os.remove(path)
    return f"Deleted {path}"

TOOLS = {t.name: t for t in [read_file, delete_file]}


def guarded_tool_node(state: MessagesState) -> dict:
    """Custom tool node with Plyra Guard evaluation."""
    messages = []

    for tool_call in state["messages"][-1].tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        tool_id = tool_call["id"]

        # Build intent string for policy evaluation
        intent = f"{tool_name} {' '.join(str(v) for v in tool_args.values())}"

        try:
            # Evaluate against policy first
            result = guard.evaluate(intent)

            if result.outcome == "BLOCK":
                content = f"[BLOCKED] {result.reason}"
            else:
                # Policy allows — execute the real tool
                actual_tool = TOOLS[tool_name]
                content = actual_tool.invoke(tool_args)

        except PolicyViolationError as e:
            content = f"[BLOCKED] {e}"
        except Exception as e:
            content = f"[ERROR] {e}"

        messages.append(
            ToolMessage(content=str(content), tool_call_id=tool_id)
        )

    return {"messages": messages}


# Wire into your graph
def should_continue(state: MessagesState) -> str:
    last = state["messages"][-1]
    return "tools" if last.tool_calls else END


graph = StateGraph(MessagesState)
graph.add_node("agent", your_llm_node)
graph.add_node("tools", guarded_tool_node)
graph.add_edge("__start__", "agent")
graph.add_conditional_edges("agent", should_continue)
graph.add_edge("tools", "agent")

app = graph.compile()
```

## What Happens on a Block

When a tool is blocked, `guarded_tool_node` returns a `ToolMessage` with a `[BLOCKED]` prefix instead of raising an exception. This means:

- The graph continues running
- The LLM sees the block message and can course-correct
- Your graph topology doesn't break

If you'd rather halt execution on a block, raise `PolicyViolationError` instead of returning a blocked message.

## With a Custom Policy

```python
from plyra_guard import Policy, Rule

policy = Policy(rules=[
    Rule(pattern=r"delete_file /etc", action="block", reason="Cannot delete system files"),
    Rule(pattern=r"delete_file /tmp", action="allow"),
    Rule(pattern=r"read_file", action="allow"),
])

guard = ActionGuard(policy=policy)
```

## Viewing Action History

```python
# After your graph runs
for action in guard.history(limit=20):
    print(f"{action.tool_name} → {action.outcome} ({action.latency_ms}ms)")
```
