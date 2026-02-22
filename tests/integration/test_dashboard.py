"""
Dashboard Integration Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

10 tests for the plyra-guard real-time dashboard module.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plyra_guard import ActionGuard
from plyra_guard.core.intent import AuditEntry
from plyra_guard.core.verdict import Verdict
from plyra_guard.dashboard import create_dashboard_router
from plyra_guard.dashboard.metrics import FeedRow, MinuteBucket, generate_chart_svg
from plyra_guard.dashboard.sse import format_sse_event

# ── Helpers ──────────────────────────────────────────────────


def _make_entry(
    verdict: Verdict = Verdict.ALLOW,
    agent_id: str = "agent-alpha",
    action_type: str = "file.read",
    risk_score: float = 0.2,
    minutes_ago: int = 0,
    rolled_back: bool = False,
    policy_triggered: str | None = None,
) -> AuditEntry:
    """Create a single AuditEntry for testing."""
    return AuditEntry(
        action_id=str(uuid.uuid4()),
        agent_id=agent_id,
        action_type=action_type,
        verdict=verdict,
        risk_score=risk_score,
        timestamp=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        rolled_back=rolled_back,
        policy_triggered=policy_triggered,
    )


def _seed_entries() -> list[AuditEntry]:
    """Create 20 seeded audit entries across all verdict types."""
    entries: list[AuditEntry] = []

    # 10 ALLOW
    for i in range(10):
        entries.append(
            _make_entry(
                verdict=Verdict.ALLOW,
                agent_id=["agent-alpha", "agent-beta", "agent-gamma"][i % 3],
                action_type=["file.read", "db.query", "api.call"][i % 3],
                risk_score=0.1 + i * 0.02,
                minutes_ago=i,
            )
        )

    # 5 BLOCK
    for i in range(5):
        entries.append(
            _make_entry(
                verdict=Verdict.BLOCK,
                agent_id=["agent-alpha", "agent-beta"][i % 2],
                action_type="file.delete",
                risk_score=0.8 + i * 0.02,
                minutes_ago=i,
                policy_triggered="block_dangerous",
            )
        )

    # 3 ESCALATE
    for i in range(3):
        entries.append(
            _make_entry(
                verdict=Verdict.ESCALATE,
                agent_id="agent-gamma",
                action_type="api.external",
                risk_score=0.6,
                minutes_ago=i,
            )
        )

    # 2 WARN
    for i in range(2):
        entries.append(
            _make_entry(
                verdict=Verdict.WARN,
                agent_id="agent-beta",
                action_type="file.write",
                risk_score=0.4,
                minutes_ago=i,
            )
        )

    return entries


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture()
def seeded_guard():
    """ActionGuard with 20 seeded audit entries and 3 agents."""
    guard = ActionGuard.default()
    entries = _seed_entries()
    for entry in entries:
        guard._audit_log.write(entry)
    return guard, entries


@pytest.fixture()
def dashboard_client(seeded_guard):
    """FastAPI TestClient with dashboard mounted."""
    guard, entries = seeded_guard
    app = FastAPI()
    app.include_router(create_dashboard_router(guard))
    client = TestClient(app)
    return client, guard, entries


# ── Tests ────────────────────────────────────────────────────


class TestDashboard:
    """Dashboard integration tests (10 tests)."""

    def test_dashboard_home_returns_200(self, dashboard_client):
        """GET /dashboard → 200, contains PLYRA branding and stat section."""
        client, _, _ = dashboard_client
        resp = client.get("/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        body = resp.text
        assert "PLYRA" in body
        assert "plyra-guard" in body
        assert "TOTAL ACTIONS" in body

    def test_dashboard_stats_returns_correct_counts(self, dashboard_client):
        """GET /dashboard/stats → 200, correct action/block/escalate counts."""
        client, _, entries = dashboard_client
        resp = client.get("/dashboard/stats")
        assert resp.status_code == 200
        body = resp.text

        total = len(entries)
        blocked = sum(1 for e in entries if e.verdict == Verdict.BLOCK)
        escalated = sum(1 for e in entries if e.verdict == Verdict.ESCALATE)

        # The stat card should contain the total count
        assert str(total) in body
        assert str(blocked) in body
        assert str(escalated) in body

    def test_dashboard_chart_returns_valid_svg(self, dashboard_client):
        """GET /dashboard/chart.svg → valid SVG with bars and title."""
        client, _, _ = dashboard_client
        resp = client.get("/dashboard/chart.svg")
        assert resp.status_code == 200
        assert "image/svg+xml" in resp.headers["content-type"]
        body = resp.text
        assert body.strip().startswith("<svg")
        assert "rect" in body
        assert "BLOCK RATE" in body

    def test_dashboard_feed_returns_recent_actions(self, dashboard_client):
        """GET /dashboard/feed → HTML with seeded verdicts and action types."""
        client, _, entries = dashboard_client
        resp = client.get("/dashboard/feed")
        assert resp.status_code == 200
        body = resp.text

        # Verify action types appear
        assert "file.delete" in body
        assert "file.read" in body

        # Verify verdict badges
        assert "ALLOW" in body
        assert "BLOCK" in body

    def test_dashboard_agents_table_shows_all_agents(self, dashboard_client):
        """GET /dashboard/agents → all 3 agent IDs, trust badges, budget SVGs."""
        client, _, _ = dashboard_client
        resp = client.get("/dashboard/agents")
        assert resp.status_code == 200
        body = resp.text

        assert "agent-alpha" in body
        assert "agent-beta" in body
        assert "agent-gamma" in body

        # Budget bar SVG elements
        assert "<svg" in body
        assert "viewBox" in body

    def test_rollback_endpoint_succeeds_for_valid_action(self, dashboard_client):
        """POST /dashboard/rollback/{id} → 200, rendered row with ROLLED BACK."""
        client, guard, entries = dashboard_client
        target = entries[0]  # an ALLOW entry

        # Mock guard.rollback to succeed
        with patch.object(guard, "rollback", return_value=True) as mock_rb:
            resp = client.post(f"/dashboard/rollback/{target.action_id}")
            assert resp.status_code == 200
            assert "ROLLED BACK" in resp.text
            mock_rb.assert_called_once_with(target.action_id)

    def test_rollback_endpoint_returns_404_for_unknown_action(self, dashboard_client):
        """POST /dashboard/rollback/valid-uuid-not-in-log → 404."""
        client, _, _ = dashboard_client
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        resp = client.post(f"/dashboard/rollback/{fake_uuid}")
        assert resp.status_code == 404
        assert "not found" in resp.text.lower()

    def test_rollback_endpoint_marks_row_as_rolled_back(self, dashboard_client):
        """After rollback, the feed row shows rolled-back styling."""
        client, guard, entries = dashboard_client
        target = entries[0]

        with patch.object(guard, "rollback", return_value=True):
            resp = client.post(f"/dashboard/rollback/{target.action_id}")
            assert resp.status_code == 200
            body = resp.text
            # The row should have the rolled-back class
            assert "rolled-back" in body
            assert "ROLLED BACK" in body

    def test_dashboard_without_extras_returns_503_with_message(self):
        """When jinja2 is missing, GET /dashboard → 503 with install instructions."""
        import plyra_guard.dashboard as dash_mod

        guard = ActionGuard.default()

        # Temporarily override to simulate missing jinja2
        original = dash_mod.create_dashboard_router

        def _mock_router(g):
            from fastapi import APIRouter
            from fastapi.responses import HTMLResponse

            router = APIRouter()

            @router.get("/dashboard", response_class=HTMLResponse)
            async def _():
                return HTMLResponse(
                    content=dash_mod.DASHBOARD_503_HTML,
                    status_code=503,
                )

            return router

        try:
            dash_mod.create_dashboard_router = _mock_router
            app = FastAPI()
            app.include_router(dash_mod.create_dashboard_router(guard))
            client = TestClient(app)
            resp = client.get("/dashboard")

            assert resp.status_code == 503
            assert "pip install plyra-guard[dashboard]" in resp.text
            assert "PLYRA" in resp.text
        finally:
            dash_mod.create_dashboard_router = original

    def test_health_endpoint_returns_correct_structure(self, dashboard_client):
        """GET /dashboard/health → JSON with status, version, actions_total, uptime_s."""
        client, _, entries = dashboard_client
        resp = client.get("/dashboard/health")
        assert resp.status_code == 200

        data = resp.json()
        assert data["status"] == "ok"
        from plyra_guard import __version__
        assert data["version"] == __version__
        assert data["actions_total"] == len(entries)
        assert isinstance(data["uptime_s"], float)
        assert data["uptime_s"] >= 0


# ── Bonus: SSE format test (not counted in the 10) ──────────


class TestSSEFormat:
    """Validate SSE event string formatting."""

    def test_sse_generator_yields_correct_event_format(self):
        """format_sse_event produces valid SSE event strings."""
        entry_dict = {
            "action_id": "test-123",
            "agent_id": "my-agent",
            "action_type": "file.read",
            "verdict": "ALLOW",
            "risk_score": 0.25,
        }
        result = format_sse_event(entry_dict)

        assert result.startswith("event: action\n")
        assert "id: test-123\n" in result
        assert "data: " in result

        # Extract JSON payload
        for line in result.split("\n"):
            if line.startswith("data: "):
                payload = json.loads(line[6:])
                assert payload["action_id"] == "test-123"
                assert payload["verdict"] == "ALLOW"
                assert payload["risk_score"] == 0.25
                break
        else:
            pytest.fail("No data line found in SSE event")

    def test_chart_svg_pure_function(self):
        """generate_chart_svg works with empty and populated buckets."""
        # Empty
        svg = generate_chart_svg([])
        assert svg.strip().startswith("<svg")
        assert "BLOCK RATE" in svg

        # Populated
        buckets = [
            MinuteBucket(
                minute=datetime.now(UTC) - timedelta(minutes=i),
                allow_count=5,
                block_count=2,
                escalate_count=1,
            )
            for i in range(60)
        ]
        svg = generate_chart_svg(buckets)
        assert svg.strip().startswith("<svg")
        assert "rect" in svg

    def test_feed_row_dataclass_defaults(self):
        """FeedRow has sensible defaults."""
        row = FeedRow()
        assert row.action_id == ""
        assert row.verdict == Verdict.ALLOW
        assert row.rolled_back is False
        assert row.has_rollback is False


# ══════════════════════════════════════════════════════════════════
# Favicon & Rollback Input Validation
# ══════════════════════════════════════════════════════════════════


class TestDashboardExtras:
    """Tests for favicon endpoint and rollback input validation."""

    def test_favicon_endpoint_returns_svg(self, dashboard_client):
        """GET /dashboard/favicon.ico → SVG with correct content type."""
        client, _, _ = dashboard_client
        resp = client.get("/dashboard/favicon.ico")
        assert resp.status_code == 200
        assert "image/svg+xml" in resp.headers["content-type"]
        assert "<svg" in resp.text or "svg" in resp.text
        assert "Cache-Control" in resp.headers

    def test_rollback_rejects_invalid_action_id(self, dashboard_client):
        """POST /dashboard/rollback/not-a-uuid → 400 bad request."""
        client, _, _ = dashboard_client
        resp = client.post("/dashboard/rollback/not-a-valid-uuid")
        assert resp.status_code == 400
        assert "Invalid action ID" in resp.text

    def test_rollback_rejects_sql_injection_attempt(self, dashboard_client):
        """POST /dashboard/rollback/'; DROP TABLE -- → 400."""
        client, _, _ = dashboard_client
        resp = client.post("/dashboard/rollback/'; DROP TABLE snapshots; --")
        assert resp.status_code == 400
