"""
Dashboard Router
~~~~~~~~~~~~~~~~

FastAPI routes for the plyra-guard monitoring dashboard.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, Response

from plyra_guard.dashboard.metrics import (
    DashboardMetrics,
    generate_chart_svg,
)

if TYPE_CHECKING:
    from plyra_guard.core.guard import ActionGuard

__all__ = ["build_router"]

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_START_TIME = time.monotonic()

_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}"
    r"-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

FAVICON_SVG = """<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>
  <rect width='32' height='32' rx='6' fill='%230d1525'/>
  <line x1='8' y1='16' x2='16' y2='7'
        stroke='%2300f5ff' stroke-width='1.5' opacity='0.4'/>
  <line x1='8' y1='16' x2='24' y2='16'
        stroke='%2300f5ff' stroke-width='1.5' opacity='0.4'/>
  <line x1='8' y1='16' x2='16' y2='25'
        stroke='%2300f5ff' stroke-width='1.5' opacity='0.4'/>
  <rect x='5' y='9' width='5' height='14' rx='2.5'
        fill='white'/>
  <circle cx='16' cy='7'  r='3' fill='%2300f5ff'/>
  <circle cx='24' cy='16' r='3' fill='%2300f5ff'/>
  <circle cx='16' cy='25' r='3' fill='%2300f5ff'/>
  <circle cx='8'  cy='16' r='2' fill='white'/>
</svg>"""


def build_router(guard: ActionGuard) -> APIRouter:
    """Build the dashboard ``APIRouter``.

    Args:
        guard: The ActionGuard instance backing the dashboard.

    Returns:
        A mounted ``APIRouter`` with prefix ``/dashboard``.
    """
    import jinja2
    from sse_starlette.sse import EventSourceResponse

    from plyra_guard.dashboard.sse import sse_event_generator

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )

    metrics = DashboardMetrics(guard._audit_log)
    router = APIRouter(tags=["dashboard"])

    # ── GET /dashboard ───────────────────────────────────

    @router.get(
        "/dashboard",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def dashboard_home() -> HTMLResponse:
        """Render the full dashboard page."""
        stats = metrics.get_stats()
        chart_svg = generate_chart_svg(metrics.get_chart_data())
        rows = metrics.get_recent_feed()
        agents = metrics.get_agent_breakdown()

        tmpl = env.get_template("index.html")
        html = tmpl.render(
            stats=stats,
            chart_svg=chart_svg,
            rows=rows,
            agents=agents,
        )
        return HTMLResponse(content=html)

    # ── GET /dashboard/stats ─────────────────────────────

    @router.get(
        "/dashboard/stats",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def dashboard_stats() -> HTMLResponse:
        """Return stat-card HTML partial."""
        stats = metrics.get_stats()
        tmpl = env.get_template("partials/stats.html")
        return HTMLResponse(
            content=tmpl.render(stats=stats),
        )

    # ── GET /dashboard/chart.svg ─────────────────────────

    @router.get(
        "/dashboard/chart.svg",
        include_in_schema=False,
    )
    async def dashboard_chart() -> Response:
        """Return block-rate SVG chart."""
        svg = generate_chart_svg(metrics.get_chart_data())
        return Response(
            content=svg,
            media_type="image/svg+xml",
        )

    # ── GET /dashboard/feed ──────────────────────────────

    @router.get(
        "/dashboard/feed",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def dashboard_feed() -> HTMLResponse:
        """Return recent feed rows partial."""
        rows = metrics.get_recent_feed()
        tmpl = env.get_template("partials/feed.html")
        return HTMLResponse(
            content=tmpl.render(rows=rows),
        )

    # ── GET /dashboard/feed/stream ───────────────────────

    @router.get(
        "/dashboard/feed/stream",
        include_in_schema=False,
    )
    async def dashboard_feed_stream() -> Any:
        """SSE stream of live audit events."""
        return EventSourceResponse(
            sse_event_generator(guard._audit_log),
            headers={"retry": "3000"},
        )

    # ── GET /dashboard/agents ────────────────────────────

    @router.get(
        "/dashboard/agents",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def dashboard_agents() -> HTMLResponse:
        """Return agent breakdown table rows."""
        agents = metrics.get_agent_breakdown()
        tmpl = env.get_template("partials/agents.html")
        return HTMLResponse(
            content=tmpl.render(agents=agents),
        )

    # ── POST /dashboard/rollback/{action_id} ─────────────

    @router.post(
        "/dashboard/rollback/{action_id}",
        response_class=HTMLResponse,
        include_in_schema=False,
    )
    async def dashboard_rollback(
        action_id: str,
    ) -> HTMLResponse:
        """Roll back an action and return the updated row."""
        # Validate UUID format before touching the guard
        if not _UUID_PATTERN.match(action_id):
            return HTMLResponse(
                content='<div class="feed-row">'
                f"Invalid action ID format: {action_id}</div>",
                status_code=400,
            )

        # Find the audit entry
        entries = guard._audit_log.query()
        entry = None
        for e in entries:
            if e.action_id == action_id:
                entry = e
                break

        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"Action {action_id} not found",
            )

        try:
            success = guard.rollback(action_id)
        except Exception as exc:
            logger.error(
                "Rollback failed for %s: %s",
                action_id,
                exc,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Rollback failed: {exc}",
            ) from exc

        if not success:
            raise HTTPException(
                status_code=500,
                detail="Rollback returned False",
            )

        # Re-render the row in rolled-back state
        from plyra_guard.dashboard.metrics import FeedRow

        row = FeedRow(
            action_id=entry.action_id,
            timestamp=entry.timestamp,
            agent_id=entry.agent_id,
            action_type=entry.action_type,
            verdict=entry.verdict,
            risk_score=entry.risk_score,
            policy_triggered=entry.policy_triggered,
            has_rollback=True,
            rolled_back=True,
        )
        tmpl = env.get_template("partials/feed_row.html")
        return HTMLResponse(
            content=tmpl.render(row=row),
        )

    # ── GET /dashboard/favicon.ico ────────────────────────

    @router.get(
        "/dashboard/favicon.ico",
        include_in_schema=False,
    )
    async def favicon() -> Response:
        """Serve the Plyra icon mark as SVG favicon."""
        return Response(
            content=FAVICON_SVG,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # ── GET /dashboard/health ────────────────────────────

    @router.get(
        "/dashboard/health",
        include_in_schema=False,
    )
    async def dashboard_health() -> JSONResponse:
        """Health-check endpoint for the nav status dot."""
        from plyra_guard import __version__

        uptime = time.monotonic() - _START_TIME
        total = len(guard._audit_log)
        return JSONResponse(
            content={
                "status": "ok",
                "version": __version__,
                "actions_total": total,
                "uptime_s": round(uptime, 2),
            },
        )

    return router
