"""
ActionGuard — Single Agent with YAML Policies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Shows loading policies from YAML config and getting actions blocked.
"""

import os
import tempfile

from plyra_guard import ActionGuard, RiskLevel
from plyra_guard.config.loader import load_config_from_dict
from plyra_guard.exceptions import ExecutionBlockedError


def main() -> None:
    print("=" * 60)
    print("ActionGuard — Single Agent with Policies")
    print("=" * 60)

    # Define policies inline (normally loaded from guard_config.yaml)
    config_data = {
        "policies": [
            {
                "name": "block_system_paths",
                "action_types": ["file.delete", "file.write"],
                "condition": "parameters.path.startswith('/etc') or parameters.path.startswith('/sys')",
                "verdict": "BLOCK",
                "message": "System path access is forbidden",
            },
            {
                "name": "escalate_high_cost",
                "action_types": ["*"],
                "condition": "estimated_cost > 0.50",
                "verdict": "ESCALATE",
                "message": "Action cost exceeds $0.50 threshold",
            },
        ],
        "rate_limits": {
            "default": "10/min",
            "per_tool": {
                "file.delete": "3/min",
            },
        },
    }

    guard = ActionGuard(config=load_config_from_dict(config_data))
    guard._audit_log._exporters.clear()  # Quiet output

    @guard.protect("file.delete", risk_level=RiskLevel.HIGH)
    def delete_file(path: str) -> bool:
        os.remove(path)
        return True

    @guard.protect("file.write", risk_level=RiskLevel.MEDIUM)
    def write_file(path: str, content: str) -> bool:
        with open(path, "w") as f:
            f.write(content)
        return True

    # 1. Try to delete a system file (should be BLOCKED by policy)
    print("\n1. Attempting to delete /etc/passwd...")
    try:
        delete_file("/etc/passwd")
        print("   ✓ Allowed (unexpected!)")
    except ExecutionBlockedError as e:
        print(f"   ✗ BLOCKED: {e.reason}")

    # 2. Try to write to a system path (should be BLOCKED)
    print("\n2. Attempting to write to /sys/config...")
    try:
        write_file("/sys/config", "hack")
        print("   ✓ Allowed (unexpected!)")
    except ExecutionBlockedError as e:
        print(f"   ✗ BLOCKED: {e.reason}")

    # 3. Normal operation (should be ALLOWED)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    tmp.close()
    print(f"\n3. Writing to temp file {tmp.name}...")
    try:
        write_file(tmp.name, "safe content")
        print("   ✓ Allowed")
    except ExecutionBlockedError as e:
        print(f"   ✗ BLOCKED: {e.reason}")

    # Cleanup
    if os.path.exists(tmp.name):
        os.remove(tmp.name)

    # 4. Show audit log
    print("\n4. Audit Log:")
    for entry in guard.get_audit_log():
        print(
            f"   [{entry.verdict.value:8s}] {entry.action_type:15s} "
            f"policy={entry.policy_triggered or 'none'}"
        )

    print("\n" + "=" * 60)
    print("Done!")


if __name__ == "__main__":
    main()
