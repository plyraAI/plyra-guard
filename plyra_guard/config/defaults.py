"""
Default Configuration
~~~~~~~~~~~~~~~~~~~~~

Sensible defaults for ActionGuard when no config file is provided.
"""

from __future__ import annotations

__all__ = ["DEFAULT_CONFIG"]

DEFAULT_CONFIG: dict = {
    "version": "1.0",
    "global": {
        "default_verdict": "ALLOW",
        "max_risk_score": 0.85,
        "max_delegation_depth": 4,
        "max_concurrent_delegations": 10,
    },
    "budget": {
        "per_task": 5.00,
        "per_agent_per_run": 1.00,
        "currency": "USD",
    },
    "rate_limits": {
        "default": "60/min",
        "per_tool": {},
    },
    "policies": [],
    "agents": [],
    "evaluators": {
        "schema_validator": {"enabled": True},
        "policy_engine": {"enabled": True},
        "risk_scorer": {"enabled": True},
        "rate_limiter": {"enabled": True},
        "cost_estimator": {"enabled": True},
        "human_gate": {"enabled": False},
    },
    "rollback": {
        "enabled": True,
        "snapshot_dir": None,
        "max_snapshots": 1000,
    },
    "observability": {
        "exporters": ["stdout"],
        "audit_log_max_entries": 10000,
    },
    "sidecar": {
        "host": "0.0.0.0",
        "port": 8080,
    },
}
