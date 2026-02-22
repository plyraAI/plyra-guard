"""
Rollback Registry
~~~~~~~~~~~~~~~~~

Maps action types to their rollback handlers, providing lookup and
registration for the rollback system.
"""

from __future__ import annotations

import logging

from plyra_guard.exceptions import RollbackHandlerNotFoundError
from plyra_guard.rollback.handlers.base_handler import BaseRollbackHandler

__all__ = ["RollbackRegistry"]

logger = logging.getLogger(__name__)


class RollbackRegistry:
    """
    Registry mapping action types to rollback handlers.

    Supports exact matches and glob pattern matching. Multiple handlers
    can be registered per action type; the first matching handler is used.
    """

    def __init__(self) -> None:
        self._handlers: list[BaseRollbackHandler] = []
        self._custom_handlers: dict[str, BaseRollbackHandler] = {}

    def register(self, handler: BaseRollbackHandler) -> None:
        """
        Register a rollback handler.

        Args:
            handler: The handler to register.
        """
        self._handlers.append(handler)
        logger.debug(
            "Registered rollback handler %s for %s",
            handler.__class__.__name__,
            handler.action_types,
        )

    def register_for_type(self, action_type: str, handler: BaseRollbackHandler) -> None:
        """
        Register a handler for a specific action type.

        Args:
            action_type: The exact action type to handle.
            handler: The handler instance.
        """
        self._custom_handlers[action_type] = handler

    def get_handler(self, action_type: str) -> BaseRollbackHandler:
        """
        Get the rollback handler for a given action type.

        Args:
            action_type: The action type to look up.

        Returns:
            The matching rollback handler.

        Raises:
            RollbackHandlerNotFoundError: If no handler is registered.
        """
        # Check custom handlers first (exact match)
        if action_type in self._custom_handlers:
            return self._custom_handlers[action_type]

        # Check registered handlers (pattern match)
        for handler in self._handlers:
            if handler.can_handle(action_type):
                return handler

        raise RollbackHandlerNotFoundError(
            f"No rollback handler registered for action type: {action_type}"
        )

    def has_handler(self, action_type: str) -> bool:
        """Check if a handler exists for the given action type."""
        if action_type in self._custom_handlers:
            return True
        return any(h.can_handle(action_type) for h in self._handlers)

    @property
    def handlers(self) -> list[BaseRollbackHandler]:
        """Return all registered handlers."""
        return list(self._handlers)

    def clear(self) -> None:
        """Remove all registered handlers."""
        self._handlers.clear()
        self._custom_handlers.clear()
