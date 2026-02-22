"""
Sidecar ASGI entry point for standalone uvicorn usage.

Usage:
    uvicorn plyra_guard.sidecar.app:app --host 127.0.0.1 --port 8080
"""

from plyra_guard.core.guard import ActionGuard
from plyra_guard.sidecar.server import create_app

# Create a default guard for standalone sidecar mode
_guard = ActionGuard.default()
app = create_app(_guard)
