"""
plyra.guard — namespace bridge for plyra-guard.

Allows importing via:
    from plyra.guard import ActionGuard

This re-exports everything from the plyra_guard package.
"""

# Re-export the entire public API from plyra_guard
from plyra_guard import *  # noqa: F401, F403
from plyra_guard import (
    ActionGuard,
    ActionIntent,
    ActionResult,
    BaseAdapter,
    BaseEvaluator,
    BaseRollbackHandler,
    RiskLevel,
    Snapshot,
    TrustLevel,
    Verdict,
    __version__,
)

__all__ = [
    "ActionGuard",
    "ActionIntent",
    "ActionResult",
    "Verdict",
    "RiskLevel",
    "TrustLevel",
    "BaseEvaluator",
    "BaseAdapter",
    "BaseRollbackHandler",
    "Snapshot",
    "__version__",
]
