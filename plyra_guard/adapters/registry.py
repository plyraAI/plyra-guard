"""
Adapter Registry
~~~~~~~~~~~~~~~~

Auto-detects the framework from an object and routes to the right adapter.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from plyra_guard.adapters.anthropic_adapter import AnthropicAdapter
from plyra_guard.adapters.autogen_adapter import AutoGenAdapter
from plyra_guard.adapters.base import BaseAdapter
from plyra_guard.adapters.crewai_adapter import CrewAIAdapter
from plyra_guard.adapters.generic_adapter import GenericAdapter
from plyra_guard.adapters.langchain_adapter import LangChainAdapter
from plyra_guard.adapters.llamaindex_adapter import LlamaIndexAdapter
from plyra_guard.adapters.openai_adapter import OpenAIAdapter
from plyra_guard.exceptions import AdapterNotFoundError

if TYPE_CHECKING:
    from plyra_guard.core.guard import ActionGuard

__all__ = ["AdapterRegistry"]

logger = logging.getLogger(__name__)


class AdapterRegistry:
    """
    Auto-detects the framework from a tool object and routes
    to the appropriate adapter.

    Adapters are tried in priority order. The GenericAdapter is
    always the last fallback.
    """

    def __init__(self) -> None:
        self._adapters: list[BaseAdapter] = [
            LangChainAdapter(),
            LlamaIndexAdapter(),
            CrewAIAdapter(),
            AutoGenAdapter(),
            OpenAIAdapter(),
            AnthropicAdapter(),
            GenericAdapter(),
        ]

    def register(self, adapter: BaseAdapter, priority: int | None = None) -> None:
        """
        Register a custom adapter.

        Args:
            adapter: The adapter instance to register.
            priority: Insert position (0 = highest priority).
                     If None, inserts before the generic adapter.
        """
        if priority is not None:
            self._adapters.insert(priority, adapter)
        else:
            # Insert before the last adapter (GenericAdapter)
            self._adapters.insert(len(self._adapters) - 1, adapter)

    def get_adapter(self, tool: Any) -> BaseAdapter:
        """
        Find the appropriate adapter for a tool object.

        Args:
            tool: The tool to find an adapter for.

        Returns:
            The matching adapter.

        Raises:
            AdapterNotFoundError: If no adapter can handle the tool.
        """
        for adapter in self._adapters:
            if adapter.can_handle(tool):
                return adapter

        raise AdapterNotFoundError(
            f"No adapter found for tool type: {type(tool).__name__}"
        )

    def wrap_tools(self, tools: list[Any], guard: ActionGuard) -> list[Any]:
        """
        Wrap a list of tools with ActionGuard protection.

        Each tool is detected and wrapped by the appropriate adapter.

        Args:
            tools: List of framework-native tool objects.
            guard: The ActionGuard instance.

        Returns:
            List of wrapped tools in their native format.
        """
        wrapped: list[Any] = []
        for tool in tools:
            adapter = self.get_adapter(tool)
            logger.debug(
                "Wrapping tool %s with %s adapter",
                getattr(tool, "name", type(tool).__name__),
                adapter.framework_name,
            )
            wrapped.append(adapter.wrap(tool, guard))
        return wrapped
