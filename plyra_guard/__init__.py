"""
plyra-guard — Action safety middleware for agentic AI.

Part of the Plyra infrastructure suite.
https://plyra.dev · https://github.com/plyraAI/plyra-guard

plyra-guard sits between any AI agent's decision engine and the actual
execution of tools/actions, providing:

- Policy-based access control
- Dynamic risk scoring
- Rate limiting and budget enforcement
- Multi-agent trust and delegation management
- Automatic rollback capabilities
- Full audit logging and observability

Quick Start::

    from plyra_guard import ActionGuard, RiskLevel

    guard = ActionGuard.default()

    @guard.protect("file.delete", risk_level=RiskLevel.HIGH)
    def delete_file(path: str) -> bool:
        import os
        os.remove(path)
        return True

    delete_file("/tmp/test.txt")

:copyright: (c) 2024 Plyra
:license: Apache-2.0
"""

from plyra_guard.adapters.base import BaseAdapter
from plyra_guard.core.guard import ActionGuard
from plyra_guard.core.intent import (
    ActionIntent,
    ActionResult,
    AgentCall,
    AuditEntry,
    AuditFilter,
    EvaluatorResult,
    GuardMetrics,
    RollbackReport,
)
from plyra_guard.core.verdict import RiskLevel, TrustLevel, Verdict
from plyra_guard.evaluators.base import BaseEvaluator
from plyra_guard.observability.exporters.stdout_exporter import (
    StdoutExporter,
)
from plyra_guard.rollback.handlers.base_handler import (
    BaseRollbackHandler,
    Snapshot,
)

__version__ = "0.1.9"
__author__ = "Plyra"
__license__ = "Apache-2.0"
__url__ = "https://plyra.dev"

__all__ = [
    # Main class
    "ActionGuard",
    # Enums
    "Verdict",
    "RiskLevel",
    "TrustLevel",
    # Data models
    "ActionIntent",
    "ActionResult",
    "AgentCall",
    "AuditEntry",
    "AuditFilter",
    "EvaluatorResult",
    "GuardMetrics",
    "RollbackReport",
    # Extension bases
    "BaseEvaluator",
    "BaseRollbackHandler",
    "BaseAdapter",
    "Snapshot",
    # Exporters
    "StdoutExporter",
    # Version
    "__version__",
]
