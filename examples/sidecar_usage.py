"""
ActionGuard — HTTP Sidecar Usage Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Shows spinning up the HTTP sidecar and the endpoints available.

To run:
    python examples/sidecar_usage.py

Then from another terminal:
    curl http://localhost:8080/health
    curl -X POST http://localhost:8080/evaluate \
         -H "Content-Type: application/json" \
         -d '{"action_type": "file.read", "parameters": {"path": "/tmp/test"}, "agent_id": "my-agent"}'
"""

from plyra_guard import ActionGuard


def main() -> None:
    print("=" * 60)
    print("ActionGuard — HTTP Sidecar")
    print("=" * 60)
    print()
    print("Starting sidecar server...")
    print()
    print("Available endpoints:")
    print("  POST /evaluate  — Evaluate an action")
    print("  POST /execute   — Execute an approved action")
    print("  POST /rollback  — Rollback action(s)")
    print("  GET  /audit     — Query audit log")
    print("  GET  /metrics   — Prometheus metrics")
    print("  GET  /health    — Health check")
    print()

    guard = ActionGuard.default()

    try:
        guard.serve(host="0.0.0.0", port=8080)
    except ImportError:
        print("ERROR: FastAPI and uvicorn are required.")
        print("Install with: pip install plyra_guard[sidecar]")
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()
