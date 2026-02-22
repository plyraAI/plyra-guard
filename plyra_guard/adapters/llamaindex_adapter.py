"""
LlamaIndex Adapter
~~~~~~~~~~~~~~~~~~

Translates LlamaIndex FunctionTool / QueryEngineTool into ActionIntent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from plyra_guard.adapters.base import BaseAdapter
from plyra_guard.core.intent import ActionIntent
from plyra_guard.core.verdict import RiskLevel

if TYPE_CHECKING:
    from plyra_guard.core.guard import ActionGuard

__all__ = ["LlamaIndexAdapter"]


def _is_llamaindex_tool(tool: Any) -> bool:
    """Check if the object is a LlamaIndex tool."""
    module = getattr(type(tool), "__module__", "") or ""
    return "llama_index" in module and hasattr(tool, "call")


class LlamaIndexAdapter(BaseAdapter):
    """Adapter for LlamaIndex FunctionTool and QueryEngineTool."""

    @property
    def framework_name(self) -> str:
        return "llamaindex"

    def can_handle(self, tool: Any) -> bool:
        return _is_llamaindex_tool(tool)

    def to_intent(
        self, tool: Any, inputs: dict[str, Any], agent_id: str
    ) -> ActionIntent:
        metadata = getattr(tool, "metadata", None)
        tool_name = getattr(metadata, "name", None) or getattr(
            tool, "name", type(tool).__name__
        )
        description = getattr(metadata, "description", "") or getattr(
            tool, "description", ""
        )

        return ActionIntent(
            action_type=f"llamaindex.{tool_name}",
            tool_name=str(tool_name),
            parameters=inputs,
            agent_id=agent_id,
            task_context=description,
            risk_level=RiskLevel.MEDIUM,
        )

    def wrap(self, tool: Any, guard: ActionGuard) -> Any:
        adapter = self
        original_call = tool.call

        def _guarded_call(*args: Any, **kwargs: Any) -> Any:
            params = dict(kwargs)
            if args:
                params["_positional_args"] = list(args)

            intent = adapter.to_intent(
                tool,
                params,
                agent_id=getattr(guard, "_default_agent_id", "default"),
            )
            return guard._execute_guarded(intent, original_call, args, kwargs)

        tool.call = _guarded_call
        return tool
