"""
ActionGuard — CrewAI Integration Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Demonstrates how to integrate ActionGuard cleanly with CrewAI by
wrapping tools before passing them to an agent.
"""

from crewai.tools import tool

from plyra_guard import ActionGuard
from plyra_guard.config.loader import load_config_from_dict


def main() -> None:
    print("=" * 60)
    print("ActionGuard — CrewAI Integration Example")
    print("=" * 60)

    # 1. Setup ActionGuard with a strict policy
    config_data = {
        "policies": [
            {
                "name": "prevent_risky_file_access",
                "action_types": ["crewai.*", "callable.*", "*.*"],
                "condition": "'.env' in parameters.get('path', '')",
                "verdict": "BLOCK",
                "message": "Access to .env files is restricted for agents.",
            },
        ],
    }

    guard = ActionGuard(config=load_config_from_dict(config_data))

    # 2. Define CrewAI Tools
    @tool("read_file")
    def read_file(path: str) -> str:
        """Reads a specified path and returns its simulated content."""
        return f"[Simulated Content for: {path}]"

    @tool("search_wiki")
    def search_wiki(topic: str) -> str:
        """Searches wiki for a topic."""
        return f"[Simulated Wiki Data for: {topic}]"

    original_tools = [read_file, search_wiki]

    # 3. Wrap tools natively with ActionGuard
    guarded_tools = guard.wrap(original_tools)

    print(f"\n[INFO] Wrapped {len(guarded_tools)} tools for CrewAI.\n")

    # 4. Now we simulate the LLM executing the tools directly to bypass API Key configs
    # (CrewAI tools use tool.invoke or tool.func in many instances)
    # We'll just call the wrapper manually here to show ActionGuard catching the invocation.

    # Tool 1: Safe invocation
    print("Simulating LLM executing a safe file read:")
    print("  read_file(path='/tmp/report.txt')  <-- Should be ALLOWED")
    try:
        # In actual CrewAI usage, the agent would just use the `guarded_tools` list
        # We manually invoke the wrapped function to test the local mechanism
        result = guarded_tools[0].run({"path": "/tmp/report.txt"})
        print(f"  --> Success. Result: {result}\n")
    except Exception as e:
        print(f"  --> Failed. {e}\n")

    # Tool 2: Blocked invocation
    print("Simulating LLM executing a blocked file read:")
    print("  read_file(path='/etc/.env')  <-- Should be BLOCKED")
    try:
        # Should raise an ActionGuard execution error due to 'prevent_risky_file_access' policy
        result = guarded_tools[0].run({"path": "/etc/.env"})
        print(f"  --> Success. Result: {result}\n")
    except Exception as e:
        # CrewAI tools often wrap output errors visually for the LLM natively
        print(f"  --> Blocked via Exception: {e}\n")

    # 5. Review Audit Log
    print("-- ActionGuard Audit Summary --")
    for entry in guard.get_audit_log():
        print(
            f"  [{entry.verdict.value:8s}] {entry.action_type:20s} "
            f"(Policy: {entry.policy_triggered or 'None'})"
        )

    print("\n" + "=" * 60)
    print("Done!")


if __name__ == "__main__":
    main()
