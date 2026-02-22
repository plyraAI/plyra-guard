"""Integration test: HTTP sidecar endpoints."""

import pytest

from plyra_guard import ActionGuard


class TestSidecar:
    """Tests for the HTTP sidecar endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client for the sidecar."""
        try:
            from fastapi.testclient import TestClient
        except ImportError:
            pytest.skip("FastAPI not installed")

        guard = ActionGuard.default()
        guard._audit_log._exporters.clear()

        from plyra_guard.sidecar.server import create_app

        app = create_app(guard)
        return TestClient(app)

    def test_health_endpoint(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_evaluate_endpoint(self, client):
        resp = client.post(
            "/evaluate",
            json={
                "action_type": "file.read",
                "parameters": {"path": "/tmp/test.txt"},
                "agent_id": "test-agent",
                "estimated_cost": 0.01,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "verdict" in data
        assert "action_id" in data

    def test_evaluate_returns_action_id(self, client):
        resp = client.post(
            "/evaluate",
            json={
                "action_type": "http.get",
                "parameters": {"url": "https://example.com"},
                "agent_id": "test-agent",
            },
        )
        data = resp.json()
        assert data["action_id"]
        assert len(data["action_id"]) == 36

    def test_audit_endpoint(self, client):
        # First create an action
        client.post(
            "/evaluate",
            json={
                "action_type": "file.read",
                "parameters": {},
                "agent_id": "test-agent",
            },
        )

        resp = client.get("/audit")
        assert resp.status_code == 200

    def test_metrics_endpoint(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_rollback_endpoint(self, client):
        resp = client.post(
            "/rollback",
            json={
                "action_id": "00000000-0000-0000-0000-000000000001",
            },
        )
        assert resp.status_code == 200

    def test_execute_unknown_action(self, client):
        resp = client.post(
            "/execute",
            json={
                "action_id": "unknown-id",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
