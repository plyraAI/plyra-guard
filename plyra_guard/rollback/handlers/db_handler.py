"""
Database Rollback Handler
~~~~~~~~~~~~~~~~~~~~~~~~~

Handles rollback for database operations by capturing row state
before mutations and restoring on rollback.
"""

from __future__ import annotations

import logging
from typing import Any

from plyra_guard.core.intent import ActionIntent
from plyra_guard.rollback.handlers.base_handler import BaseRollbackHandler, Snapshot

__all__ = ["DbRollbackHandler"]

logger = logging.getLogger(__name__)


class DbRollbackHandler(BaseRollbackHandler):
    """
    Rollback handler for database operations.

    Supports:
    - db.insert: Deletes the inserted row.
    - db.update: Restores the original row values.
    - db.delete: Re-inserts the deleted row.

    Note: This handler stores row data in the snapshot. The actual
    DB operations must be provided via a callback since ActionGuard
    is framework-agnostic and does not couple to any specific DB driver.
    """

    def __init__(
        self,
        query_callback: Any | None = None,
        execute_callback: Any | None = None,
    ) -> None:
        """
        Args:
            query_callback: Callable(sql, params) -> list[dict] for reading rows.
            execute_callback: Callable(sql, params) -> None for writing rows.
        """
        self._query = query_callback
        self._execute = execute_callback

    @property
    def action_types(self) -> list[str]:
        return ["db.insert", "db.update", "db.delete"]

    def capture(self, intent: ActionIntent) -> Snapshot:
        """Capture row state before the DB operation."""
        state: dict[str, Any] = {
            "table": intent.parameters.get("table", ""),
            "action_type": intent.action_type,
        }

        if intent.action_type in ("db.update", "db.delete"):
            # Capture the rows that will be affected
            where = intent.parameters.get("where", {})
            state["where"] = where
            if self._query and where:
                try:
                    table = state["table"]
                    conditions = " AND ".join(f"{k} = ?" for k in where.keys())
                    sql = f"SELECT * FROM {table} WHERE {conditions}"
                    rows = self._query(sql, list(where.values()))
                    state["original_rows"] = rows
                except Exception as exc:
                    logger.warning("DB capture failed: %s", exc)
                    state["original_rows"] = []
            else:
                state["original_rows"] = []

        elif intent.action_type == "db.insert":
            state["insert_data"] = intent.parameters.get("data", {})
            state["primary_key"] = intent.parameters.get("primary_key", "id")

        return Snapshot(
            action_id=intent.action_id,
            action_type=intent.action_type,
            state=state,
        )

    def restore(self, snapshot: Snapshot) -> bool:
        """Restore the database to its pre-action state."""
        state = snapshot.state
        table = state.get("table", "")
        action_type = state.get("action_type", "")

        if not self._execute:
            logger.error("No execute callback configured for DB rollback")
            return False

        try:
            if action_type == "db.insert":
                # Delete the inserted row
                pk = state.get("primary_key", "id")
                insert_data = state.get("insert_data", {})
                if pk in insert_data:
                    sql = f"DELETE FROM {table} WHERE {pk} = ?"
                    self._execute(sql, [insert_data[pk]])
                    return True

            elif action_type == "db.delete":
                # Re-insert the deleted rows
                rows = state.get("original_rows", [])
                for row in rows:
                    cols = ", ".join(row.keys())
                    placeholders = ", ".join("?" * len(row))
                    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
                    self._execute(sql, list(row.values()))
                return True

            elif action_type == "db.update":
                # Restore original row values
                rows = state.get("original_rows", [])
                where = state.get("where", {})
                for row in rows:
                    set_clause = ", ".join(f"{k} = ?" for k in row.keys())
                    where_clause = " AND ".join(f"{k} = ?" for k in where.keys())
                    sql = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
                    params = list(row.values()) + list(where.values())
                    self._execute(sql, params)
                return True

        except Exception as exc:
            logger.error("DB rollback failed: %s", exc)
            return False

        return False
