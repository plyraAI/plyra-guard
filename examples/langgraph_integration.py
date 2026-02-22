"""
ActionGuard — LangGraph Integration Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Demonstrates how to integrate ActionGuard cleanly with LangGraph by
creating a custom node. This node intercepts tool calls in the graph
state, evaluates them with ActionGuard, and blocks unsafe actions natively.

WHY USE A CUSTOM NODE INSTEAD OF guard.wrap()?
----------------------------------------------
Newer versions of LangGraph and LangChain's native `ToolNode` utilize internal
tracking mechanics and strict validation of `Runnable` attributes that conflict
when transparently monkeypatching tools with standard wrappers like `guard.wrap()`.

The recommended pattern for LangGraph specifically is to parse the Native Graph State
before tool execution using a wrapper node (like `guarded_tool_node` below). This
evaluates the `ActionIntent` against the guard cluster and correctly yields standard
`ToolMessage` responses back to the LLM when blocked, avoiding internal graph crashes.
"""

from typing import Any

from plyra_guard import ActionGuard
from plyra_guard.config.loader import load_config_from_dict
from plyra_guard.core.intent import ActionIntent
from plyra_guard.core.verdict import Verdict

try:
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.tools import tool
    from langgraph.graph import MessagesState
except ImportError:
    print("This example requires langchain-core and langgraph.")
    print("Run: pip install langchain-core langgraph")
    import sys

    sys.exit(1)


def main() -> None:
    print("=" * 60)
    print("ActionGuard — LangGraph Integration Example")
    print("=" * 60)

    # 1. Setup ActionGuard with a strict policy
    config_data = {
        "policies": [
            {
                "name": "block_destructive_commands",
                "action_types": ["execute_command"],
                "condition": "'rm ' in parameters.get('command', '')",
                "verdict": "BLOCK",
                "message": "Destructive shell commands are forbidden",
            },
        ],
    }

    guard = ActionGuard(config=load_config_from_dict(config_data))

    # 2. Define standard LangChain tools
    @tool
    def execute_command(command: str) -> str:
        """Execute a shell command."""
        return f"Executed: {command}"

    @tool
    def search_web(query: str) -> str:
        """Search the web."""
        return f"Results for: {query}"

    tools = {
        "execute_command": execute_command,
        "search_web": search_web,
    }

    # 3. Create a Guarded Tool execution node for LangGraph
    def guarded_tool_node(state: MessagesState) -> dict[str, Any]:
        last_message = state["messages"][-1]
        results: list[ToolMessage] = []

        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return {"messages": results}

        for tcall in last_message.tool_calls:
            # 1. Check with ActionGuard
            intent = ActionIntent(
                action_type=tcall["name"],
                tool_name=tcall["name"],
                parameters=tcall["args"],
                agent_id="langgraph-agent",
            )
            eval_result = guard.evaluate(intent)

            if eval_result.verdict == Verdict.BLOCK:
                # 2. Return a blocked message to the LLM
                block_msg = ToolMessage(
                    content=f"Action blocked by policy: {eval_result.reason}",
                    tool_call_id=tcall["id"],
                    name=tcall["name"],
                )
                results.append(block_msg)
            else:
                # 3. Safe to execute, run the tool natively
                tool_obj = tools[tcall["name"]]
                res = tool_obj.invoke(tcall["args"])
                success_msg = ToolMessage(
                    content=str(res),
                    tool_call_id=tcall["id"],
                    name=tcall["name"],
                )
                results.append(success_msg)

        return {"messages": results}

    # 4. Simulate a LangGraph state update containing two tool calls
    unsafe_call = {
        "name": "execute_command",
        "args": {"command": "rm -rf /"},
        "id": "call_123456",
        "type": "tool_call",
    }

    safe_call = {
        "name": "search_web",
        "args": {"query": "AI safety guidelines"},
        "id": "call_654321",
        "type": "tool_call",
    }

    msg = AIMessage(
        content="",
        tool_calls=[unsafe_call, safe_call],
    )

    print("\n[INFO] Simulating a LangGraph state update containing two tool calls:")
    print("       1. execute_command(command='rm -rf /')  <-- Should be BLOCKED")
    print("       2. search_web(query='AI safety guidelines') <-- Should be ALLOWED\n")

    state: MessagesState = {"messages": [msg]}

    # 5. Execute the ToolNode wrapper directly
    # (In a real Graph you'd use workflow.add_node("tools", guarded_tool_node))
    node_result = guarded_tool_node(state)

    for m in node_result.get("messages", []):
        print(f"[{m.name}] Tool response:")
        print(f"  --> {m.content}\n")

    # 6. Print Audit Log
    print("-- ActionGuard Audit Summary --")
    for entry in guard.get_audit_log():
        print(
            f"  [{entry.verdict.value:8s}] {entry.action_type:15s} "
            f"(Policy: {entry.policy_triggered or 'None'})"
        )

    print("\n" + "=" * 60)
    print("Done!")


if __name__ == "__main__":
    main()
