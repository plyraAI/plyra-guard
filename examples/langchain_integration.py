"""
ActionGuard — LangChain Integration Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Shows wrapping LangChain tools with guard.wrap() and a policy
that blocks one of them.

NOTE: This example requires langchain to be installed.
      Run: pip install langchain
      If not installed, the example will simulate the behavior.
"""

from plyra_guard import ActionGuard
from plyra_guard.config.loader import load_config_from_dict


def main() -> None:
    print("=" * 60)
    print("ActionGuard — LangChain Integration Example")
    print("=" * 60)

    config_data = {
        "policies": [
            {
                "name": "block_dangerous_commands",
                "action_types": ["langchain.*", "generic.*"],
                "condition": "parameters.command.startswith('rm ') if 'command' in parameters else False",
                "verdict": "BLOCK",
                "message": "Dangerous shell commands are forbidden",
            },
        ],
    }

    guard = ActionGuard(config=load_config_from_dict(config_data))
    guard._audit_log._exporters.clear()

    # Simulate LangChain-style tools without requiring the import
    print("\n  (Simulating LangChain tools with generic callables)")

    def search_web(query: str) -> str:
        """Search the web for information."""
        return f"Results for: {query}"

    def run_command(command: str) -> str:
        """Execute a shell command."""
        return f"Output of: {command}"

    def read_file(path: str) -> str:
        """Read a file from disk."""
        return f"Contents of {path}"

    # Wrap all tools
    tools = [search_web, run_command, read_file]
    wrapped = guard.wrap(tools)

    print(f"\n  Wrapped {len(wrapped)} tools with ActionGuard")

    # Use the wrapped tools
    print("\n1. Search web (should be ALLOWED):")
    try:
        result = wrapped[0](query="AI safety")
        print(f"   ✓ {result}")
    except Exception as e:
        print(f"   ✗ {e}")

    print("\n2. Read file (should be ALLOWED):")
    try:
        result = wrapped[2](path="/tmp/test.txt")
        print(f"   ✓ {result}")
    except Exception as e:
        print(f"   ✗ {e}")

    print("\n3. Run safe command (should be ALLOWED):")
    try:
        result = wrapped[1](command="echo hello")
        print(f"   ✓ {result}")
    except Exception as e:
        print(f"   ✗ {e}")

    # Show audit
    print("\n── Audit Summary ──")
    for entry in guard.get_audit_log():
        print(f"  [{entry.verdict.value:8s}] {entry.action_type}")

    print("\n" + "=" * 60)
    print("Done!")


if __name__ == "__main__":
    main()
