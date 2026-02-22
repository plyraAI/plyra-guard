"""
ActionGuard — Single Agent Basic Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The simplest possible usage: one guard, one protected function, one call.
"""

import os
import tempfile

from plyra_guard import ActionGuard, RiskLevel


def main() -> None:
    # Create a guard with sensible defaults (no config needed)
    guard = ActionGuard.default()

    # Protect a function with the @guard.protect decorator
    @guard.protect("file.read", risk_level=RiskLevel.LOW)
    def read_file(path: str) -> str:
        """Read and return the contents of a file."""
        with open(path) as f:
            return f.read()

    @guard.protect("file.write", risk_level=RiskLevel.MEDIUM)
    def write_file(path: str, content: str) -> bool:
        """Write content to a file."""
        with open(path, "w") as f:
            f.write(content)
        return True

    @guard.protect("file.delete", risk_level=RiskLevel.HIGH)
    def delete_file(path: str) -> bool:
        """Delete a file from the filesystem."""
        os.remove(path)
        return True

    # Create a temp file for testing
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Hello, ActionGuard!")
        temp_path = f.name

    print("=" * 60)
    print("ActionGuard — Single Agent Basic Example")
    print("=" * 60)

    # 1. Read (low risk — should be allowed)
    print("\n1. Reading file (LOW risk)...")
    try:
        content = read_file(temp_path)
        print(f"   ✓ Read successful: {content!r}")
    except Exception as e:
        print(f"   ✗ Blocked: {e}")

    # 2. Write (medium risk — should be allowed)
    print("\n2. Writing file (MEDIUM risk)...")
    try:
        write_file(temp_path, "Updated by ActionGuard!")
        print("   ✓ Write successful")
    except Exception as e:
        print(f"   ✗ Blocked: {e}")

    # 3. Read again to verify
    print("\n3. Reading updated file...")
    try:
        content = read_file(temp_path)
        print(f"   ✓ Updated content: {content!r}")
    except Exception as e:
        print(f"   ✗ Blocked: {e}")

    # 4. Delete (high risk — should be allowed but logged)
    print("\n4. Deleting file (HIGH risk)...")
    try:
        delete_file(temp_path)
        print("   ✓ Delete successful")
    except Exception as e:
        print(f"   ✗ Blocked: {e}")

    # 5. Show audit log
    print("\n5. Audit Log:")
    entries = guard.get_audit_log()
    for entry in entries:
        print(
            f"   [{entry.verdict.value:8s}] {entry.action_type:15s} "
            f"risk={entry.risk_score:.2f}"
        )

    # 6. Show metrics
    print("\n6. Metrics:")
    metrics = guard.get_metrics()
    print(f"   Total actions: {metrics.total_actions}")
    print(f"   Allowed: {metrics.allowed_actions}")
    print(f"   Blocked: {metrics.blocked_actions}")
    print(f"   Avg risk score: {metrics.avg_risk_score:.2f}")

    print("\n" + "=" * 60)
    print("Done!")


if __name__ == "__main__":
    main()
