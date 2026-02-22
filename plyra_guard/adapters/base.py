"""
Base Adapter
~~~~~~~~~~~~

Abstract base class for framework adapters that translate
framework-native tool objects into ActionIntent objects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from plyra_guard.core.intent import ActionIntent

if TYPE_CHECKING:
    from plyra_guard.core.guard import ActionGuard

__all__ = ["BaseAdapter"]


class BaseAdapter(ABC):
    """
    Abstract base class for framework adapters.

    Each adapter translates a framework-specific tool object into
    a standard ActionIntent, and can wrap tools to inject ActionGuard
    protection into the execution path.
    """

    @property
    @abstractmethod
    def framework_name(self) -> str:
        """Human-readable name of the framework this adapter supports."""
        ...

    @abstractmethod
    def can_handle(self, tool: Any) -> bool:
        """
        Check if this adapter can handle the given tool object.

        Args:
            tool: A framework-native tool object.

        Returns:
            True if this adapter can translate/wrap this tool.
        """
        ...

    @abstractmethod
    def to_intent(
        self, tool: Any, inputs: dict[str, Any], agent_id: str
    ) -> ActionIntent:
        """
        Convert a framework-native tool invocation to an ActionIntent.

        Args:
            tool: The framework-native tool object.
            inputs: The inputs/arguments to the tool.
            agent_id: The ID of the calling agent.

        Returns:
            An ActionIntent representing the tool invocation.
        """
        ...

    @abstractmethod
    def wrap(self, tool: Any, guard: ActionGuard) -> Any:
        """
        Wrap a tool to inject ActionGuard into its execution path.

        The returned object must be in the SAME framework-native format
        so it can be used as a drop-in replacement.

        Args:
            tool: The framework-native tool to wrap.
            guard: The ActionGuard instance to use for protection.

        Returns:
            A wrapped tool in the same framework-native format.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} framework={self.framework_name!r}>"
