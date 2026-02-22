"""
ActionGuard — AutoGen Integration Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Demonstrates how to integrate ActionGuard cleanly with AutoGen by
creating a custom tool and wrapping it before registering with an agent.
"""

from typing import Annotated

import autogen

from plyra_guard import ActionGuard
from plyra_guard.config.loader import load_config_from_dict


def main() -> None:
    print("=" * 60)
    print("ActionGuard — AutoGen Integration Example")
    print("=" * 60)

    # 1. Setup ActionGuard with a strict policy
    config_data = {
        "policies": [
            {
                "name": "block_destructive_commands",
                "action_types": [
                    "*.execute_command",
                    "callable.execute_command",
                    "execute_command",
                ],
                "condition": "'rm ' in parameters.get('cmd', '')",
                "verdict": "BLOCK",
                "message": "Destructive shell commands are forbidden",
            },
        ],
    }

    guard = ActionGuard(config=load_config_from_dict(config_data))

    # 2. Define standard functions
    def execute_command(cmd: Annotated[str, "Shell command to execute"]) -> str:
        """Execute a shell command."""
        return f"Executed: {cmd}"

    def search_web(query: Annotated[str, "Search query"]) -> str:
        """Search the web."""
        return f"Results for: {query}"

    # 3. Wrap tools with ActionGuard
    wrapped_execute = guard.wrap([execute_command])[0]
    wrapped_search = guard.wrap([search_web])[0]

    # 4. Create an AutoGen agent that uses these tools
    user_proxy = autogen.UserProxyAgent(
        name="user_proxy",
        is_termination_msg=lambda x: (
            x.get("content", "") and x.get("content", "").rstrip().endswith("TERMINATE")
        ),
        human_input_mode="NEVER",
        max_consecutive_auto_reply=2,
    )

    # Register wrapped tools natively with the agent
    user_proxy.register_function(
        function_map={
            "execute_command": wrapped_execute,
            "search_web": wrapped_search,
        }
    )

    print("\n[INFO] Wrapped tools registered with AutoGen UserProxyAgent.\n")

    # 5. Simulate an LLM attempting to call the tools by manually injecting tool calls into the agent's context
    # and having it execute them. (We bypass OpenAI API explicitly to keep this example standalone)
    unsafe_call = {
        "function": {
            "name": "execute_command",
            "arguments": '{"cmd": "rm -rf /"}',
        },
        "id": "call_123456",
        "type": "function",
    }

    safe_call = {
        "function": {
            "name": "search_web",
            "arguments": '{"query": "AI safety guidelines"}',
        },
        "id": "call_654321",
        "type": "function",
    }

    print("Simulating AutoGen executing a safe tool call:")
    print("  search_web(query='AI safety guidelines') <-- Should be ALLOWED")
    success, result_safe = user_proxy.execute_function(safe_call["function"])
    print(f"  --> {result_safe}\n")

    print("Simulating AutoGen executing an unsafe tool call:")
    print("  execute_command(cmd='rm -rf /')  <-- Should be BLOCKED")
    try:
        success, result_unsafe = user_proxy.execute_function(unsafe_call["function"])
        print(f"  --> {result_unsafe}\n")
    except Exception as e:
        print(f"  --> Blocked via Exception: {e}\n")

    # 6. Print Audit Log
    print("-- ActionGuard Audit Summary --")
    for entry in guard.get_audit_log():
        print(
            f"  [{entry.verdict.value:8s}] {entry.action_type:25s} "
            f"(Policy: {entry.policy_triggered or 'None'})"
        )

    print("\n" + "=" * 60)
    print("Done!")


if __name__ == "__main__":
    main()
