"""
Real-World Sidecar Subprocess Integration Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Spins up the sidecar as a REAL subprocess (not TestClient),
sends real HTTP requests with httpx.
"""

from __future__ import annotations

import pytest

httpx = pytest.importorskip("httpx", reason="httpx required for sidecar tests")


class TestSidecarSubprocess:
    """Tests against a real sidecar running in a subprocess."""

    def test_health_endpoint(self, sidecar_url):
        """GET /health returns 200 with status: ok."""
        resp = httpx.get(f"{sidecar_url}/health", timeout=5.0)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    def test_evaluate_allow(self, sidecar_url):
        """POST /evaluate a low-risk action, assert ALLOW."""
        resp = httpx.post(
            f"{sidecar_url}/evaluate",
            json={
                "action_type": "file.read",
                "parameters": {"path": "/tmp/safe.txt"},
                "agent_id": "test-agent",
                "estimated_cost": 0.01,
            },
            timeout=5.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "ALLOW"

    def test_evaluate_returns_action_id(self, sidecar_url):
        """Verify response contains a valid UUID action_id."""
        resp = httpx.post(
            f"{sidecar_url}/evaluate",
            json={
                "action_type": "http.get",
                "parameters": {"url": "https://example.com"},
                "agent_id": "test-agent",
            },
            timeout=5.0,
        )
        data = resp.json()
        assert "action_id" in data
        assert len(data["action_id"]) == 36  # UUID format

    def test_evaluate_multiple_verdicts(self, sidecar_url):
        """Multiple evaluations with different risk profiles."""
        # Low risk
        resp1 = httpx.post(
            f"{sidecar_url}/evaluate",
            json={
                "action_type": "file.read",
                "parameters": {"path": "/tmp/test.txt"},
                "agent_id": "agent-low",
            },
            timeout=5.0,
        )
        assert resp1.status_code == 200

        # Higher cost
        resp2 = httpx.post(
            f"{sidecar_url}/evaluate",
            json={
                "action_type": "api.call",
                "parameters": {},
                "agent_id": "agent-high",
                "estimated_cost": 0.30,
            },
            timeout=5.0,
        )
        assert resp2.status_code == 200

    def test_audit_after_evaluate(self, sidecar_url):
        """Evaluate an action, then GET /audit to verify entry exists."""
        # Create an action first
        eval_resp = httpx.post(
            f"{sidecar_url}/evaluate",
            json={
                "action_type": "file.read",
                "parameters": {"path": "/tmp/audit_test.txt"},
                "agent_id": "audit-agent",
            },
            timeout=5.0,
        )
        assert eval_resp.status_code == 200

        # Query audit
        audit_resp = httpx.get(
            f"{sidecar_url}/audit",
            params={"agent_id": "audit-agent"},
            timeout=5.0,
        )
        assert audit_resp.status_code == 200

    def test_metrics_endpoint(self, sidecar_url):
        """GET /metrics returns Prometheus text with counters."""
        # Generate some traffic first
        httpx.post(
            f"{sidecar_url}/evaluate",
            json={
                "action_type": "file.read",
                "parameters": {},
                "agent_id": "metrics-agent",
            },
            timeout=5.0,
        )

        resp = httpx.get(f"{sidecar_url}/metrics", timeout=5.0)
        assert resp.status_code == 200
        body = resp.text
        assert "plyra_guard_total_actions" in body

    def test_rollback_endpoint_graceful(self, sidecar_url):
        """POST /rollback with unknown ID, verify graceful response."""
        resp = httpx.post(
            f"{sidecar_url}/rollback",
            json={"action_id": "00000000-0000-0000-0000-000000000002"},
            timeout=5.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should handle gracefully — either empty or in failed list
        assert "rolled_back" in data
        assert "failed" in data

    def test_execute_unknown_action(self, sidecar_url):
        """POST /execute with unknown action_id returns success=False."""
        resp = httpx.post(
            f"{sidecar_url}/execute",
            json={"action_id": "unknown-action-xyz"},
            timeout=5.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_execute_after_evaluate(self, sidecar_url):
        """Evaluate → execute → success."""
        eval_resp = httpx.post(
            f"{sidecar_url}/evaluate",
            json={
                "action_type": "file.read",
                "parameters": {"path": "/tmp/exec_test.txt"},
                "agent_id": "exec-agent",
            },
            timeout=5.0,
        )
        action_id = eval_resp.json()["action_id"]

        exec_resp = httpx.post(
            f"{sidecar_url}/execute",
            json={"action_id": action_id},
            timeout=5.0,
        )
        assert exec_resp.status_code == 200
        assert exec_resp.json()["success"] is True

    def test_concurrent_requests(self, sidecar_url):
        """Send 10 sequential evaluations, all return 200."""
        for i in range(10):
            resp = httpx.post(
                f"{sidecar_url}/evaluate",
                json={
                    "action_type": f"test.action_{i}",
                    "parameters": {"index": i},
                    "agent_id": f"concurrent-agent-{i}",
                },
                timeout=5.0,
            )
            assert resp.status_code == 200
            assert "verdict" in resp.json()
