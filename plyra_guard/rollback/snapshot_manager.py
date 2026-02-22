"""
Snapshot Manager
~~~~~~~~~~~~~~~~

Manages pre-execution state snapshots with SQLite persistence
and in-memory write-through cache for the rollback system.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import threading
from collections import OrderedDict
from datetime import UTC, datetime

from plyra_guard.core.intent import ActionIntent
from plyra_guard.rollback.handlers.base_handler import Snapshot
from plyra_guard.rollback.registry import RollbackRegistry

__all__ = ["SnapshotManager"]

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS snapshots (
    action_id    TEXT PRIMARY KEY,
    action_type  TEXT NOT NULL,
    agent_id     TEXT NOT NULL,
    snapshot_data TEXT NOT NULL,
    captured_at  TEXT NOT NULL,
    expires_at   TEXT,
    restored     INTEGER DEFAULT 0
)
"""


def _default_db_path() -> str:
    """Return the default SQLite database path."""
    home = os.path.expanduser("~")
    plyra_dir = os.path.join(home, ".plyra")
    os.makedirs(plyra_dir, exist_ok=True)
    return os.path.join(plyra_dir, "snapshots.db")


class SnapshotManager:
    """
    Manages capture and retrieval of pre-execution state snapshots.

    Uses SQLite for durable persistence and an in-memory OrderedDict
    as a write-through cache for fast reads.
    """

    def __init__(
        self,
        registry: RollbackRegistry | None = None,
        max_in_memory: int = 1000,
        storage_dir: str | None = None,
        db_path: str | None = None,
    ) -> None:
        self._registry = registry
        self._max_in_memory = max_in_memory
        self._snapshots: OrderedDict[str, Snapshot] = OrderedDict()
        self._lock = asyncio.Lock()
        self._sync_lock = threading.RLock()  # sync-only fallback

        # Resolve DB path
        self._db_path = db_path or _default_db_path()
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)

        # Initialize SQLite
        self._init_db()

        # Legacy: keep storage_dir compatibility but don't use for new ops
        self._storage_dir = storage_dir
        if self._storage_dir:
            os.makedirs(self._storage_dir, exist_ok=True)

    def _init_db(self) -> None:
        """Create the snapshots table if it doesn't exist."""
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(_CREATE_TABLE_SQL)
            conn.commit()
        finally:
            conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a new SQLite connection."""
        return sqlite3.connect(self._db_path)

    def capture(self, intent: ActionIntent) -> Snapshot | None:
        """
        Capture the pre-execution state for an action.

        Uses the appropriate rollback handler to capture state.
        Returns None if no handler is registered for the action type.
        """
        if self._registry and not self._registry.has_handler(intent.action_type):
            return None

        snapshot: Snapshot
        if self._registry:
            handler = self._registry.get_handler(intent.action_type)
            snapshot = handler.capture(intent)
        else:
            # Create a basic snapshot when no registry is provided
            snapshot = Snapshot(
                action_id=intent.action_id,
                action_type=intent.action_type,
                state=dict(intent.parameters),
                metadata={"agent_id": intent.agent_id},
            )

        with self._sync_lock:
            self._snapshots[intent.action_id] = snapshot
            # Evict oldest from cache if over limit
            while len(self._snapshots) > self._max_in_memory:
                self._snapshots.popitem(last=False)

        # Persist to SQLite
        self._persist_to_db(snapshot, intent.agent_id)

        logger.debug(
            "Captured snapshot for action %s (%s)",
            intent.action_id,
            intent.action_type,
        )
        return snapshot

    async def capture_async(self, intent: ActionIntent) -> Snapshot | None:
        """Async version of capture."""
        if self._registry and not self._registry.has_handler(intent.action_type):
            return None

        snapshot: Snapshot
        if self._registry:
            handler = self._registry.get_handler(intent.action_type)
            snapshot = handler.capture(intent)
        else:
            snapshot = Snapshot(
                action_id=intent.action_id,
                action_type=intent.action_type,
                state=dict(intent.parameters),
                metadata={"agent_id": intent.agent_id},
            )

        async with self._lock:
            self._snapshots[intent.action_id] = snapshot
            while len(self._snapshots) > self._max_in_memory:
                self._snapshots.popitem(last=False)

        # Persist to SQLite (run in thread to avoid blocking)
        await asyncio.to_thread(self._persist_to_db, snapshot, intent.agent_id)

        return snapshot

    def get(self, action_id: str) -> Snapshot | None:
        """
        Retrieve a snapshot by action_id.

        Args:
            action_id: The action whose snapshot to retrieve.

        Returns:
            The captured Snapshot, or None if not found.
        """
        with self._sync_lock:
            if action_id in self._snapshots:
                return self._snapshots[action_id]

        # Check SQLite
        snapshot = self._load_from_db(action_id)
        if snapshot is not None:
            return snapshot

        return None

    async def get_async(self, action_id: str) -> Snapshot | None:
        """Async version of get."""
        async with self._lock:
            if action_id in self._snapshots:
                return self._snapshots[action_id]

        return await asyncio.to_thread(self._load_from_db, action_id)

    def mark_restored(self, action_id: str) -> bool:
        """Mark a snapshot as restored in the database."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "UPDATE snapshots SET restored = 1 WHERE action_id = ?",
                (action_id,),
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    async def mark_restored_async(self, action_id: str) -> bool:
        """Async version of mark_restored."""
        return await asyncio.to_thread(self.mark_restored, action_id)

    def cleanup(self, older_than_hours: int = 24) -> int:
        """
        Delete snapshots older than the specified hours.

        Returns the count of deleted rows.
        """
        cutoff = datetime.now(UTC)
        from datetime import timedelta

        cutoff = cutoff - timedelta(hours=older_than_hours)
        cutoff_iso = cutoff.isoformat()

        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "DELETE FROM snapshots WHERE captured_at < ?",
                (cutoff_iso,),
            )
            conn.commit()
            deleted = cursor.rowcount

            # Also clean cache
            with self._sync_lock:
                to_remove = [
                    aid
                    for aid, snap in self._snapshots.items()
                    if snap.captured_at < cutoff
                ]
                for aid in to_remove:
                    del self._snapshots[aid]

            return deleted
        finally:
            conn.close()

    def remove(self, action_id: str) -> None:
        """Remove a snapshot after successful rollback."""
        with self._sync_lock:
            self._snapshots.pop(action_id, None)

        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM snapshots WHERE action_id = ?", (action_id,))
            conn.commit()
        finally:
            conn.close()

    def list_action_ids(self) -> list[str]:
        """Return all action_ids that have snapshots."""
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT action_id FROM snapshots").fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()

    def _persist_to_db(self, snapshot: Snapshot, agent_id: str = "") -> None:
        """Persist a snapshot to SQLite."""
        conn = self._get_conn()
        try:
            data = json.dumps(
                {
                    "state": snapshot.state,
                    "metadata": snapshot.metadata,
                },
                default=str,
            )
            conn.execute(
                """INSERT OR REPLACE INTO snapshots
                   (action_id, action_type, agent_id, snapshot_data, captured_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    snapshot.action_id,
                    snapshot.action_type,
                    agent_id or snapshot.metadata.get("agent_id", ""),
                    data,
                    snapshot.captured_at.isoformat(),
                ),
            )
            conn.commit()
        except sqlite3.Error as exc:
            logger.error("Failed to persist snapshot %s: %s", snapshot.action_id, exc)
        finally:
            conn.close()

    def _load_from_db(self, action_id: str) -> Snapshot | None:
        """Load a snapshot from SQLite."""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT action_id, action_type, snapshot_data, captured_at "
                "FROM snapshots WHERE action_id = ?",
                (action_id,),
            ).fetchone()
            if row is None:
                return None

            data = json.loads(row[2])
            return Snapshot(
                action_id=row[0],
                action_type=row[1],
                captured_at=datetime.fromisoformat(row[3]),
                state=data.get("state", {}),
                metadata=data.get("metadata", {}),
            )
        except (sqlite3.Error, json.JSONDecodeError, KeyError) as exc:
            logger.error("Failed to load snapshot %s: %s", action_id, exc)
            return None
        finally:
            conn.close()

    def clear(self) -> None:
        """Clear all snapshots from memory and database."""
        with self._sync_lock:
            self._snapshots.clear()

        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM snapshots")
            conn.commit()
        finally:
            conn.close()
