"""
plyra-guard Dashboard
~~~~~~~~~~~~~~~~~~~~~

Real-time monitoring dashboard for plyra-guard.
Requires the ``[dashboard]`` extras to be installed.

Part of the Plyra infrastructure suite.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

__all__ = ["create_dashboard_router"]

# ── 503 fallback page (shown when dashboard extras missing) ──

DASHBOARD_503_HTML = """\
<!DOCTYPE html>
<html>
<head>
  <title>plyra-guard &middot; Dashboard Not Installed</title>
  <meta name="theme-color" content="#050810">
</head>
<body style="
  background: #050810;
  color: #4a7a9b;
  font-family: 'Courier New', monospace;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  margin: 0;
  text-align: center;
  gap: 16px;
">
  <div style="color:#00f5ff; font-size:14px;\
 letter-spacing:4px; font-weight:700">
    &#9650; PLYRA
  </div>
  <div style="color:#ffffff; font-size:22px; margin: 8px 0">
    Dashboard not installed
  </div>
  <div style="font-size:13px; line-height:2.2; color:#4a7a9b">
    The dashboard requires additional dependencies.<br>
    Run the following and restart the server:
  </div>
  <div style="
    background:#0d1525; border:1px solid #1a3050;
    border-left: 3px solid #00f5ff;
    padding: 16px 32px; border-radius: 6px;
    color: #ffffff; font-size: 14px;
    letter-spacing: 1px; margin: 8px 0;
  ">
    pip install plyra-guard[dashboard]
  </div>
  <div style="font-size:11px; letter-spacing:3px;\
 color:#1a3050; margin-top:40px">
    PLYRA &middot; AGENTIC INFRASTRUCTURE
  </div>
</body>
</html>
"""


def create_dashboard_router(guard: Any) -> Any:
    """Create the dashboard FastAPI router.

    If ``jinja2`` or ``sse_starlette`` are not installed,
    returns a stub router that serves a 503 page with
    installation instructions.

    Args:
        guard: The ActionGuard instance to visualise.

    Returns:
        A FastAPI ``APIRouter`` instance.
    """
    try:
        import jinja2  # noqa: F401
        import sse_starlette  # noqa: F401
    except ImportError:
        from fastapi import APIRouter
        from fastapi.responses import HTMLResponse

        router = APIRouter()

        @router.get(
            "/dashboard",
            response_class=HTMLResponse,
            include_in_schema=False,
        )
        async def dashboard_not_installed() -> HTMLResponse:
            return HTMLResponse(
                content=DASHBOARD_503_HTML,
                status_code=503,
            )

        return router

    from plyra_guard.dashboard.router import build_router

    return build_router(guard)
