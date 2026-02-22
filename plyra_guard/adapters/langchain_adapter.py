"""
LangChain Adapter
~~~~~~~~~~~~~~~~~

Translates LangChain BaseTool / StructuredTool into ActionIntent
and wraps them with ActionGuard protection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from plyra_guard.adapters.base import BaseAdapter
from plyra_guard.core.intent import ActionIntent
from plyra_guard.core.verdict import RiskLevel

if TYPE_CHECKING:
    from plyra_guard.core.guard import ActionGuard

__all__ = ["LangChainAdapter"]


def _is_langchain_tool(tool: Any) -> bool:
    """Check if the object is a LangChain tool without importing langchain."""
    type_name = type(tool).__name__
    module = getattr(type(tool), "__module__", "") or ""
    return (
        type_name in ("BaseTool", "StructuredTool", "Tool") and "langchain" in module
    ) or (
        hasattr(tool, "name")
        and hasattr(tool, "description")
        and hasattr(tool, "_run")
        and "langchain" in module
    )


class LangChainAdapter(BaseAdapter):
    """Adapter for LangChain BaseTool and StructuredTool."""

    @property
    def framework_name(self) -> str:
        return "langchain"

    def can_handle(self, tool: Any) -> bool:
        return _is_langchain_tool(tool)

    def to_intent(
        self, tool: Any, inputs: dict[str, Any], agent_id: str
    ) -> ActionIntent:
        tool_name = getattr(tool, "name", type(tool).__name__)
        description = getattr(tool, "description", "")

        return ActionIntent(
            action_type=f"langchain.{tool_name}",
            tool_name=tool_name,
            parameters=inputs,
            agent_id=agent_id,
            task_context=description,
            risk_level=RiskLevel.MEDIUM,
        )

    def wrap(self, tool: Any, guard: ActionGuard) -> Any:
        """
        Wrap a LangChain tool with ActionGuard protection.

        Returns a new tool with the same interface but guarded execution.
        """
        adapter = self

        original_run = tool._run
        getattr(tool, "name", "unknown")

        def _guarded_run(*args: Any, **kwargs: Any) -> Any:
            # Merge args into kwargs for intent
            params = dict(kwargs)
            if args:
                params["_positional_args"] = list(args)

            intent = adapter.to_intent(
                tool,
                params,
                agent_id=getattr(guard, "_default_agent_id", "default"),
            )

            result = guard._execute_guarded(intent, original_run, args, kwargs)
            return result

        tool._run = _guarded_run
        tool._guarded = True  # type: ignore[attr-defined]
        return tool
