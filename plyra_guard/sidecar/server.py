"""
Sidecar Server
~~~~~~~~~~~~~~

FastAPI HTTP sidecar server for language-agnostic ActionGuard access.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from plyra_guard.core.guard import ActionGuard

__all__ = ["create_app"]


def create_app(guard: ActionGuard) -> Any:
    """
    Create a FastAPI application wired to the given ActionGuard instance.

    Args:
        guard: The ActionGuard instance to expose via HTTP.

    Returns:
        A FastAPI application instance.
    """
    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        raise ImportError(
            "FastAPI is required for the sidecar server. "
            "Install with: pip install plyra_guard[sidecar]"
        )

    app = FastAPI(
        title="ActionGuard Sidecar",
        description="HTTP API for ActionGuard agent action control",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from plyra_guard.sidecar.routes import register_routes

    register_routes(app, guard)

    # Mount dashboard (gracefully degrades if extras missing)
    try:
        from plyra_guard.dashboard import create_dashboard_router

        app.include_router(create_dashboard_router(guard))
    except Exception:
        pass  # dashboard extras not installed — skip silently

    return app
