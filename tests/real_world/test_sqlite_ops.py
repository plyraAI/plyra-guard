"""
Real-World SQLite Integration Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tests ActionGuard against a real SQLite database.
No DB mocks — actual INSERTs, UPDATEs, DELETEs, and rollbacks.
"""

from __future__ import annotations

import sqlite3

from plyra_guard import ActionGuard, RiskLevel
from plyra_guard.rollback.handlers.db_handler import DbRollbackHandler


class TestSQLiteOperations:
    """Tests that exercise real SQLite CRUD through guard.protect()."""

    def _make_callbacks(self, conn: sqlite3.Connection):
        """Create query and execute callbacks for the DbRollbackHandler."""

        def query_cb(sql: str, params: list) -> list[dict]:
            cursor = conn.execute(sql, params)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

        def execute_cb(sql: str, params: list) -> None:
            conn.execute(sql, params)
            conn.commit()

        return query_cb, execute_cb

    def _make_guard(self, conn: sqlite3.Connection) -> ActionGuard:
        """Create a guard wired to the given SQLite connection."""
        query_cb, execute_cb = self._make_callbacks(conn)
        handler = DbRollbackHandler(
            query_callback=query_cb,
            execute_callback=execute_cb,
        )
        guard = ActionGuard.default()
        guard._audit_log._exporters.clear()
        # Clear the default handlers and register ours with real callbacks
        guard._rollback_registry.clear()
        guard._rollback_registry.register(handler)
        return guard

    def _count_rows(self, conn: sqlite3.Connection, table: str) -> int:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def _get_user(self, conn: sqlite3.Connection, user_id: int) -> dict | None:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM users WHERE id = ?", [user_id]).fetchone()
        if row is None:
            return None
        return dict(row)

    def test_insert_and_verify(self, sqlite_db):
        """Guard-protected INSERT, verify row with SELECT."""
        _, conn = sqlite_db
        guard = self._make_guard(conn)

        @guard.protect("db.insert", risk_level=RiskLevel.MEDIUM)
        def insert_user(table: str, data: dict, primary_key: str = "id") -> bool:
            cols = ", ".join(data.keys())
            placeholders = ", ".join("?" * len(data))
            conn.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                list(data.values()),
            )
            conn.commit()
            return True

        insert_user(
            table="users",
            data={"id": 1, "name": "Alice", "email": "alice@example.com", "age": 30},
            primary_key="id",
        )

        user = self._get_user(conn, 1)
        assert user is not None
        assert user["name"] == "Alice"
        assert user["email"] == "alice@example.com"
        assert user["age"] == 30

    def test_update_and_verify(self, sqlite_db):
        """INSERT → guard-protected UPDATE, verify new values."""
        _, conn = sqlite_db
        guard = self._make_guard(conn)

        conn.execute(
            "INSERT INTO users (id, name, email, age) VALUES (?, ?, ?, ?)",
            [1, "Bob", "bob@example.com", 25],
        )
        conn.commit()

        @guard.protect("db.update", risk_level=RiskLevel.MEDIUM)
        def update_user(table: str, data: dict, where: dict) -> bool:
            set_clause = ", ".join(f"{k} = ?" for k in data.keys())
            where_clause = " AND ".join(f"{k} = ?" for k in where.keys())
            conn.execute(
                f"UPDATE {table} SET {set_clause} WHERE {where_clause}",
                list(data.values()) + list(where.values()),
            )
            conn.commit()
            return True

        update_user(
            table="users",
            data={"name": "Robert", "age": 26},
            where={"id": 1},
        )

        user = self._get_user(conn, 1)
        assert user["name"] == "Robert"
        assert user["age"] == 26
        assert user["email"] == "bob@example.com"  # unchanged

    def test_delete_and_verify(self, sqlite_db):
        """INSERT → guard-protected DELETE, verify row gone."""
        _, conn = sqlite_db
        guard = self._make_guard(conn)

        conn.execute(
            "INSERT INTO users (id, name, email) VALUES (?, ?, ?)",
            [1, "Charlie", "charlie@example.com"],
        )
        conn.commit()
        assert self._count_rows(conn, "users") == 1

        @guard.protect("db.delete", risk_level=RiskLevel.HIGH)
        def delete_user(table: str, where: dict) -> bool:
            where_clause = " AND ".join(f"{k} = ?" for k in where.keys())
            conn.execute(
                f"DELETE FROM {table} WHERE {where_clause}",
                list(where.values()),
            )
            conn.commit()
            return True

        delete_user(table="users", where={"id": 1})
        assert self._count_rows(conn, "users") == 0

    def test_rollback_insert(self, sqlite_db):
        """INSERT → rollback → row no longer in DB."""
        _, conn = sqlite_db
        guard = self._make_guard(conn)

        @guard.protect("db.insert", risk_level=RiskLevel.MEDIUM)
        def insert_user(table: str, data: dict, primary_key: str = "id") -> bool:
            cols = ", ".join(data.keys())
            placeholders = ", ".join("?" * len(data))
            conn.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                list(data.values()),
            )
            conn.commit()
            return True

        insert_user(
            table="users",
            data={"id": 10, "name": "Temporary", "email": "temp@example.com"},
            primary_key="id",
        )
        assert self._get_user(conn, 10) is not None

        entries = guard.get_audit_log()
        action_id = entries[-1].action_id

        success = guard.rollback(action_id)
        assert success is True

        # Row should be gone
        assert self._get_user(conn, 10) is None

    def test_rollback_update(self, sqlite_db):
        """UPDATE → rollback → original values restored."""
        _, conn = sqlite_db
        guard = self._make_guard(conn)

        conn.execute(
            "INSERT INTO users (id, name, email, age) VALUES (?, ?, ?, ?)",
            [1, "Diana", "diana@example.com", 28],
        )
        conn.commit()

        @guard.protect("db.update", risk_level=RiskLevel.MEDIUM)
        def update_user(table: str, data: dict, where: dict) -> bool:
            set_clause = ", ".join(f"{k} = ?" for k in data.keys())
            where_clause = " AND ".join(f"{k} = ?" for k in where.keys())
            conn.execute(
                f"UPDATE {table} SET {set_clause} WHERE {where_clause}",
                list(data.values()) + list(where.values()),
            )
            conn.commit()
            return True

        update_user(
            table="users",
            data={"name": "CHANGED", "age": 99},
            where={"id": 1},
        )

        user = self._get_user(conn, 1)
        assert user["name"] == "CHANGED"

        entries = guard.get_audit_log()
        action_id = entries[-1].action_id

        success = guard.rollback(action_id)
        assert success is True

        user = self._get_user(conn, 1)
        assert user["name"] == "Diana"
        assert user["age"] == 28

    def test_rollback_delete(self, sqlite_db):
        """DELETE → rollback → row restored."""
        _, conn = sqlite_db
        guard = self._make_guard(conn)

        conn.execute(
            "INSERT INTO users (id, name, email, age) VALUES (?, ?, ?, ?)",
            [1, "Eve", "eve@example.com", 35],
        )
        conn.commit()

        @guard.protect("db.delete", risk_level=RiskLevel.HIGH)
        def delete_user(table: str, where: dict) -> bool:
            where_clause = " AND ".join(f"{k} = ?" for k in where.keys())
            conn.execute(
                f"DELETE FROM {table} WHERE {where_clause}",
                list(where.values()),
            )
            conn.commit()
            return True

        delete_user(table="users", where={"id": 1})
        assert self._get_user(conn, 1) is None

        entries = guard.get_audit_log()
        action_id = entries[-1].action_id

        success = guard.rollback(action_id)
        assert success is True

        user = self._get_user(conn, 1)
        assert user is not None
        assert user["name"] == "Eve"
        assert user["age"] == 35

    def test_multi_row_operations(self, sqlite_db):
        """Insert multiple rows and verify all exist."""
        _, conn = sqlite_db
        guard = self._make_guard(conn)

        @guard.protect("db.insert", risk_level=RiskLevel.MEDIUM)
        def insert_user(table: str, data: dict, primary_key: str = "id") -> bool:
            cols = ", ".join(data.keys())
            placeholders = ", ".join("?" * len(data))
            conn.execute(
                f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
                list(data.values()),
            )
            conn.commit()
            return True

        for i in range(5):
            insert_user(
                table="users",
                data={
                    "id": i + 1,
                    "name": f"User_{i}",
                    "email": f"user{i}@test.com",
                    "age": 20 + i,
                },
                primary_key="id",
            )

        assert self._count_rows(conn, "users") == 5

        # Verify audit log recorded all 5
        entries = guard.get_audit_log()
        assert len(entries) == 5
        assert all(e.action_type == "db.insert" for e in entries)
