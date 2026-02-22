"""Tests for the rollback system."""

import os

import pytest

from plyra_guard import ActionIntent
from plyra_guard.exceptions import RollbackHandlerNotFoundError
from plyra_guard.rollback.handlers.file_handler import FileRollbackHandler
from plyra_guard.rollback.registry import RollbackRegistry


class TestFileRollbackHandler:
    """Tests for the file rollback handler."""

    def test_rollback_file_delete(self, temp_file, temp_dir):
        """Test restoring a deleted file."""
        handler = FileRollbackHandler(snapshot_dir=temp_dir)

        intent = ActionIntent(
            action_type="file.delete",
            tool_name="delete_file",
            parameters={"path": temp_file},
            agent_id="agent-1",
        )

        # Capture snapshot
        snapshot = handler.capture(intent)
        assert snapshot.state["existed"] is True

        # Delete the file
        os.remove(temp_file)
        assert not os.path.exists(temp_file)

        # Rollback
        success = handler.restore(snapshot)
        assert success is True
        assert os.path.exists(temp_file)

        with open(temp_file) as f:
            assert f.read() == "original content"

    def test_rollback_file_write(self, temp_file, temp_dir):
        """Test restoring a file after overwrite."""
        handler = FileRollbackHandler(snapshot_dir=temp_dir)

        intent = ActionIntent(
            action_type="file.write",
            tool_name="write_file",
            parameters={"path": temp_file},
            agent_id="agent-1",
        )

        # Capture snapshot
        snapshot = handler.capture(intent)

        # Overwrite the file
        with open(temp_file, "w") as f:
            f.write("modified content")

        # Rollback
        success = handler.restore(snapshot)
        assert success is True

        with open(temp_file) as f:
            assert f.read() == "original content"

    def test_rollback_file_create(self, temp_dir):
        """Test removing a created file."""
        handler = FileRollbackHandler(snapshot_dir=temp_dir)
        new_file = os.path.join(temp_dir, "new_file.txt")

        intent = ActionIntent(
            action_type="file.create",
            tool_name="create_file",
            parameters={"path": new_file},
            agent_id="agent-1",
        )

        # Capture snapshot (file doesn't exist yet)
        snapshot = handler.capture(intent)

        # Create the file
        with open(new_file, "w") as f:
            f.write("new content")

        # Rollback should delete the created file
        success = handler.restore(snapshot)
        assert success is True
        assert not os.path.exists(new_file)

    def test_capture_nonexistent_file(self, temp_dir):
        """Test capturing when file doesn't exist."""
        handler = FileRollbackHandler(snapshot_dir=temp_dir)

        intent = ActionIntent(
            action_type="file.read",
            tool_name="read_file",
            parameters={"path": "/nonexistent/path.txt"},
            agent_id="agent-1",
        )

        snapshot = handler.capture(intent)
        assert snapshot.state["existed"] is False


class TestRollbackRegistry:
    """Tests for the rollback registry."""

    def test_register_and_get_handler(self):
        reg = RollbackRegistry()
        handler = FileRollbackHandler()
        reg.register(handler)

        result = reg.get_handler("file.delete")
        assert result is handler

    def test_handler_not_found_raises(self):
        reg = RollbackRegistry()
        with pytest.raises(RollbackHandlerNotFoundError):
            reg.get_handler("unknown.action")

    def test_has_handler(self):
        reg = RollbackRegistry()
        handler = FileRollbackHandler()
        reg.register(handler)

        assert reg.has_handler("file.delete") is True
        assert reg.has_handler("unknown.action") is False

    def test_clear_registry(self):
        reg = RollbackRegistry()
        reg.register(FileRollbackHandler())
        reg.clear()
        assert reg.has_handler("file.delete") is False


# ══════════════════════════════════════════════════════════════════
# SnapshotManager SQLite persistence tests
# ══════════════════════════════════════════════════════════════════


class TestSnapshotManagerSQLite:
    """Tests for SQLite-backed SnapshotManager."""

    def test_snapshot_manager_persists_to_sqlite(self, tmp_path):
        """Snapshot survives a new SnapshotManager instance."""
        from plyra_guard.rollback.snapshot_manager import SnapshotManager

        db_path = str(tmp_path / "snapshots.db")
        sm1 = SnapshotManager(db_path=db_path)
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read_file",
            parameters={"path": "/tmp/test.txt"},
            agent_id="test-agent",
        )
        snapshot = sm1.capture(intent)
        assert snapshot is not None

        # Create a new instance pointing to the same DB
        sm2 = SnapshotManager(db_path=db_path)
        retrieved = sm2.get(snapshot.action_id)
        assert retrieved is not None
        assert retrieved.action_id == snapshot.action_id

    def test_snapshot_manager_cleanup_removes_old_entries(self, tmp_path):
        """cleanup() removes old entries from SQLite."""
        from plyra_guard.rollback.snapshot_manager import SnapshotManager

        db_path = str(tmp_path / "snapshots.db")
        sm = SnapshotManager(db_path=db_path)
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read_file",
            parameters={"path": "/tmp/test.txt"},
            agent_id="test-agent",
        )
        sm.capture(intent)
        # cleanup with older_than_hours=0 removes everything
        count = sm.cleanup(older_than_hours=0)
        assert count >= 1

    @pytest.mark.asyncio
    async def test_snapshot_manager_async_capture(self, tmp_path):
        """Async capture persists and is retrievable."""
        from plyra_guard.rollback.snapshot_manager import SnapshotManager

        db_path = str(tmp_path / "snapshots.db")
        sm = SnapshotManager(db_path=db_path)
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read_file",
            parameters={"path": "/tmp/test.txt"},
            agent_id="test-agent",
        )
        snapshot = await sm.capture_async(intent)
        assert snapshot is not None
        retrieved = await sm.get_async(snapshot.action_id)
        assert retrieved is not None
        assert retrieved.action_id == snapshot.action_id
