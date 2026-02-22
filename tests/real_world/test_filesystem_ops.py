"""
Real-World Filesystem Integration Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tests ActionGuard against actual filesystem operations.
No mocks — real files created, read, written, deleted, and rolled back.
"""

from __future__ import annotations

import os

import pytest

from plyra_guard import RiskLevel
from plyra_guard.exceptions import ExecutionBlockedError


class TestFilesystemOperations:
    """Tests that exercise real file CRUD through guard.protect()."""

    def test_create_read_write_delete_lifecycle(
        self, guard_with_policies, tmp_workspace
    ):
        """Full CRUD lifecycle with on-disk verification at each step."""
        guard = guard_with_policies
        file_path = os.path.join(tmp_workspace, "lifecycle_test.txt")

        @guard.protect("file.create", risk_level=RiskLevel.MEDIUM)
        def create_file(path: str, content: str) -> bool:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return True

        @guard.protect("file.read", risk_level=RiskLevel.LOW)
        def read_file(path: str) -> str:
            with open(path, encoding="utf-8") as f:
                return f.read()

        @guard.protect("file.write", risk_level=RiskLevel.MEDIUM)
        def write_file(path: str, content: str) -> bool:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return True

        @guard.protect("file.delete", risk_level=RiskLevel.HIGH)
        def delete_file(path: str) -> bool:
            os.remove(path)
            return True

        # CREATE
        create_file(file_path, "Hello, ActionGuard!")
        assert os.path.exists(file_path)

        # READ
        content = read_file(file_path)
        assert content == "Hello, ActionGuard!"

        # WRITE (overwrite)
        write_file(file_path, "Updated content")
        assert read_file(file_path) == "Updated content"

        # DELETE
        delete_file(file_path)
        assert not os.path.exists(file_path)

    def test_rollback_restores_overwritten_file(
        self, guard_with_policies, tmp_workspace
    ):
        """Write → rollback → original content restored on disk."""
        guard = guard_with_policies
        file_path = os.path.join(tmp_workspace, "rollback_write.txt")

        # Seed the file with original content
        with open(file_path, "w") as f:
            f.write("original content")

        @guard.protect("file.write", risk_level=RiskLevel.MEDIUM)
        def write_file(path: str, content: str) -> bool:
            with open(path, "w") as f:
                f.write(content)
            return True

        # Overwrite
        write_file(file_path, "OVERWRITTEN DATA")
        assert open(file_path).read() == "OVERWRITTEN DATA"

        # Get the action_id from audit log
        entries = guard.get_audit_log()
        action_id = entries[-1].action_id

        # Rollback
        success = guard.rollback(action_id)
        assert success is True

        # Verify original content restored on disk
        with open(file_path) as f:
            assert f.read() == "original content"

    def test_rollback_restores_deleted_file(self, guard_with_policies, tmp_workspace):
        """Delete → rollback → file exists again with original content."""
        guard = guard_with_policies
        file_path = os.path.join(tmp_workspace, "rollback_delete.txt")

        with open(file_path, "w") as f:
            f.write("precious data")

        @guard.protect("file.delete", risk_level=RiskLevel.HIGH)
        def delete_file(path: str) -> bool:
            os.remove(path)
            return True

        delete_file(file_path)
        assert not os.path.exists(file_path)

        entries = guard.get_audit_log()
        action_id = entries[-1].action_id

        success = guard.rollback(action_id)
        assert success is True
        assert os.path.exists(file_path)

        with open(file_path) as f:
            assert f.read() == "precious data"

    def test_rollback_removes_created_file(self, guard_with_policies, tmp_workspace):
        """Create → rollback → file no longer on disk."""
        guard = guard_with_policies
        file_path = os.path.join(tmp_workspace, "rollback_create.txt")

        @guard.protect("file.create", risk_level=RiskLevel.MEDIUM)
        def create_file(path: str) -> bool:
            with open(path, "w") as f:
                f.write("new file")
            return True

        create_file(file_path)
        assert os.path.exists(file_path)

        entries = guard.get_audit_log()
        action_id = entries[-1].action_id

        success = guard.rollback(action_id)
        assert success is True
        assert not os.path.exists(file_path)

    def test_directory_operations(self, guard_with_policies, tmp_workspace):
        """Create and manage directories with nested files."""
        guard = guard_with_policies
        dir_path = os.path.join(tmp_workspace, "nested", "subdir")

        @guard.protect("file.create", risk_level=RiskLevel.MEDIUM)
        def create_dir_with_files(path: str) -> bool:
            os.makedirs(path, exist_ok=True)
            for i in range(3):
                with open(os.path.join(path, f"file_{i}.txt"), "w") as f:
                    f.write(f"content {i}")
            return True

        create_dir_with_files(dir_path)
        assert os.path.isdir(dir_path)
        assert len(os.listdir(dir_path)) == 3

        for i in range(3):
            fp = os.path.join(dir_path, f"file_{i}.txt")
            with open(fp) as f:
                assert f.read() == f"content {i}"

    def test_policy_blocks_system_path(self, guard_with_policies):
        """Attempting /etc/passwd delete raises ExecutionBlockedError."""
        guard = guard_with_policies

        @guard.protect("file.delete", risk_level=RiskLevel.HIGH)
        def delete_file(path: str) -> bool:
            os.remove(path)
            return True

        with pytest.raises(ExecutionBlockedError) as exc_info:
            delete_file("/etc/passwd")

        assert (
            "forbidden" in exc_info.value.reason.lower()
            or "System path" in exc_info.value.reason
        )

    def test_audit_log_records_all_ops(self, guard_with_policies, tmp_workspace):
        """Run 5 ops, verify audit log has 5 entries with correct types."""
        guard = guard_with_policies

        file_path = os.path.join(tmp_workspace, "audit_test.txt")

        @guard.protect("file.create", risk_level=RiskLevel.LOW)
        def create(path: str) -> bool:
            with open(path, "w") as f:
                f.write("a")
            return True

        @guard.protect("file.read", risk_level=RiskLevel.LOW)
        def read(path: str) -> str:
            return open(path).read()

        @guard.protect("file.write", risk_level=RiskLevel.LOW)
        def write(path: str, data: str) -> bool:
            with open(path, "w") as f:
                f.write(data)
            return True

        @guard.protect("file.delete", risk_level=RiskLevel.MEDIUM)
        def delete(path: str) -> bool:
            os.remove(path)
            return True

        create(file_path)
        read(file_path)
        write(file_path, "b")
        read(file_path)
        delete(file_path)

        entries = guard.get_audit_log()
        assert len(entries) == 5

        expected_types = [
            "file.create",
            "file.read",
            "file.write",
            "file.read",
            "file.delete",
        ]
        actual_types = [e.action_type for e in entries]
        assert actual_types == expected_types

    def test_large_file_rollback(self, guard_with_policies, tmp_workspace):
        """Rollback works on a 1 MB file."""
        guard = guard_with_policies
        file_path = os.path.join(tmp_workspace, "large_file.bin")

        original_data = b"X" * (1024 * 1024)  # 1 MB
        with open(file_path, "wb") as f:
            f.write(original_data)

        @guard.protect("file.write", risk_level=RiskLevel.MEDIUM)
        def overwrite(path: str) -> bool:
            with open(path, "wb") as f:
                f.write(b"Y" * 100)
            return True

        overwrite(file_path)
        assert os.path.getsize(file_path) == 100

        entries = guard.get_audit_log()
        guard.rollback(entries[-1].action_id)

        with open(file_path, "rb") as f:
            restored = f.read()
        assert len(restored) == 1024 * 1024
        assert restored == original_data
