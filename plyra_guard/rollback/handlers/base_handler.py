"""
Base Rollback Handler
~~~~~~~~~~~~~~~~~~~~~

Abstract base class for rollback handlers that restore state after
a guarded action is reversed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from plyra_guard.core.intent import ActionIntent

__all__ = ["BaseRollbackHandler", "Snapshot"]


@dataclass
class Snapshot:
    """
    Captured pre-execution state for rollback purposes.

    Attributes:
        action_id: The action this snapshot corresponds to.
        action_type: The type of action that was performed.
        captured_at: When the snapshot was taken.
        state: The captured state data.
        metadata: Additional information for the handler.
    """

    action_id: str
    action_type: str
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    state: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseRollbackHandler(ABC):
    """
    Abstract base class for rollback handlers.

    Each handler is responsible for:
    1. Capturing pre-execution state (capture)
    2. Restoring that state if rollback is requested (restore)
    3. Declaring which action types it handles

    Subclasses must implement capture() and restore().
    """

    @property
    @abstractmethod
    def action_types(self) -> list[str]:
        """List of action_type patterns this handler supports."""
        ...

    @abstractmethod
    def capture(self, intent: ActionIntent) -> Snapshot:
        """
        Capture the pre-execution state before the action runs.

        Args:
            intent: The action about to be executed.

        Returns:
            A Snapshot containing the state needed for rollback.
        """
        ...

    @abstractmethod
    def restore(self, snapshot: Snapshot) -> bool:
        """
        Restore the captured state, undoing the action.

        Args:
            snapshot: The previously captured state.

        Returns:
            True if rollback succeeded, False otherwise.
        """
        ...

    def can_handle(self, action_type: str) -> bool:
        """Check if this handler supports the given action type."""
        from fnmatch import fnmatch

        return any(fnmatch(action_type, pattern) for pattern in self.action_types)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} action_types={self.action_types!r}>"
