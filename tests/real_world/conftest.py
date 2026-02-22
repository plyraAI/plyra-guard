"""
Shared fixtures for real-world integration tests.

These fixtures create REAL infrastructure — temp directories,
SQLite databases, subprocess sidecar servers — no mocking of
the tools themselves.
"""

from __future__ import annotations

import os
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections.abc import Generator

import pytest

from plyra_guard import ActionGuard
from plyra_guard.config.loader import load_config_from_dict
from plyra_guard.rollback.handlers.db_handler import DbRollbackHandler

# ── Filesystem Fixtures ──────────────────────────────────────────


@pytest.fixture
def tmp_workspace() -> Generator[str, None, None]:
    """Create a real temp directory, auto-cleaned."""
    d = tempfile.mkdtemp(prefix="plyra_guard_rw_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ── SQLite Fixtures ──────────────────────────────────────────────


@pytest.fixture
def sqlite_db(tmp_workspace) -> Generator[tuple[str, sqlite3.Connection], None, None]:
    """
    Create a real SQLite database with a `users` table.

    Yields (db_path, connection). Closes and removes on teardown.
    """
    db_path = os.path.join(tmp_workspace, "test.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            age INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    yield db_path, conn
    conn.close()


# ── Guard Fixtures ───────────────────────────────────────────────


@pytest.fixture
def guard_with_policies(tmp_workspace) -> ActionGuard:
    """ActionGuard configured with blocking policies and file rollback."""
    config_data = {
        "policies": [
            {
                "name": "block_etc",
                "action_types": ["file.delete", "file.write", "file.read"],
                "condition": "parameters.path.startswith('/etc') or parameters.path.startswith('C:\\\\Windows')",
                "verdict": "BLOCK",
                "message": "System path access forbidden",
            },
            {
                "name": "block_high_cost",
                "action_types": ["*"],
                "condition": "estimated_cost > 1.00",
                "verdict": "BLOCK",
                "message": "Cost exceeds $1.00",
            },
        ],
        "rollback": {
            "enabled": True,
            "snapshot_dir": os.path.join(tmp_workspace, "snapshots"),
        },
    }
    guard = ActionGuard(config=load_config_from_dict(config_data))
    guard._audit_log._exporters.clear()
    return guard


@pytest.fixture
def guard_with_db(sqlite_db) -> tuple[ActionGuard, sqlite3.Connection]:
    """
    ActionGuard configured with a real SQLite DbRollbackHandler.

    Yields (guard, sqlite_connection).
    """
    db_path, conn = sqlite_db

    def query_cb(sql: str, params: list) -> list[dict]:
        cursor = conn.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def execute_cb(sql: str, params: list) -> None:
        conn.execute(sql, params)
        conn.commit()

    handler = DbRollbackHandler(
        query_callback=query_cb,
        execute_callback=execute_cb,
    )

    guard = ActionGuard.default()
    guard._audit_log._exporters.clear()
    guard._rollback_registry.register(handler)
    return guard, conn


# ── Sidecar Subprocess Fixture ───────────────────────────────────


def _find_free_port() -> int:
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def sidecar_url() -> Generator[str, None, None]:
    """
    Spin up a real sidecar subprocess on a random port.

    Polls /health until it responds, then yields the base URL.
    Kills the subprocess on teardown.
    """
    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "plyra_guard.sidecar.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        if sys.platform == "win32"
        else 0,
    )

    # Wait for the sidecar to come up
    import httpx

    deadline = time.time() + 15  # 15s timeout
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{url}/health", timeout=2.0)
            if resp.status_code == 200:
                break
        except (httpx.ConnectError, httpx.ReadError, httpx.ConnectTimeout):
            pass
        time.sleep(0.3)
    else:
        proc.kill()
        stdout, stderr = proc.communicate()
        pytest.fail(
            f"Sidecar failed to start on port {port}.\n"
            f"stdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        )

    yield url

    # Teardown
    if sys.platform == "win32":
        proc.terminate()
    else:
        os.kill(proc.pid, signal.SIGTERM)
    proc.wait(timeout=5)
