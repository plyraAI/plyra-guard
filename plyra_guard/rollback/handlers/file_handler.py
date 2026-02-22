"""
File Rollback Handler
~~~~~~~~~~~~~~~~~~~~~

Handles rollback for file operations: create, write, delete.
Captures file content before modification and restores it on rollback.
"""

from __future__ import annotations

import os
import shutil
import tempfile

from plyra_guard.core.intent import ActionIntent
from plyra_guard.rollback.handlers.base_handler import BaseRollbackHandler, Snapshot

__all__ = ["FileRollbackHandler"]


class FileRollbackHandler(BaseRollbackHandler):
    """
    Rollback handler for file system operations.

    Supports:
    - file.delete: Restores the deleted file from a captured copy.
    - file.write: Restores the original file content.
    - file.create: Deletes the created file.
    """

    def __init__(self, snapshot_dir: str | None = None) -> None:
        self._snapshot_dir = snapshot_dir or tempfile.mkdtemp(
            prefix="plyra_guard_snapshots_"
        )
        os.makedirs(self._snapshot_dir, exist_ok=True)

    @property
    def action_types(self) -> list[str]:
        return ["file.delete", "file.write", "file.create"]

    def _snapshot_path(self, action_id: str) -> str:
        """Get the snapshot file path for a given action_id."""
        return os.path.join(self._snapshot_dir, f"{action_id}.snapshot")

    def capture(self, intent: ActionIntent) -> Snapshot:
        """Capture file state before the action."""
        file_path = intent.parameters.get("path", "")
        state: dict = {"original_path": file_path, "existed": False}

        if file_path and os.path.exists(file_path):
            state["existed"] = True
            # Copy the file to snapshot storage
            snap_path = self._snapshot_path(intent.action_id)
            if os.path.isfile(file_path):
                shutil.copy2(file_path, snap_path)
                state["snapshot_path"] = snap_path
                state["is_file"] = True
            elif os.path.isdir(file_path):
                if os.path.exists(snap_path):
                    shutil.rmtree(snap_path)
                shutil.copytree(file_path, snap_path)
                state["snapshot_path"] = snap_path
                state["is_file"] = False

        return Snapshot(
            action_id=intent.action_id,
            action_type=intent.action_type,
            state=state,
        )

    def restore(self, snapshot: Snapshot) -> bool:
        """Restore the file to its pre-action state."""
        state = snapshot.state
        original_path = state.get("original_path", "")
        action_type = snapshot.action_type

        if action_type == "file.create":
            # Undo creation by deleting the file
            if original_path and os.path.exists(original_path):
                if os.path.isfile(original_path):
                    os.remove(original_path)
                else:
                    shutil.rmtree(original_path)
            return True

        if action_type in ("file.delete", "file.write"):
            # Restore from snapshot
            snap_path = state.get("snapshot_path")
            if not snap_path or not os.path.exists(snap_path):
                return state.get("existed", False) is False

            if state.get("is_file", True):
                # Ensure parent directory exists
                parent = os.path.dirname(original_path)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                shutil.copy2(snap_path, original_path)
            else:
                if os.path.exists(original_path):
                    shutil.rmtree(original_path)
                shutil.copytree(snap_path, original_path)
            return True

        return False
