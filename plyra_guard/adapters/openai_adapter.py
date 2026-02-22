"""
OpenAI Adapter
~~~~~~~~~~~~~~

Translates OpenAI function call dicts into ActionIntent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from plyra_guard.adapters.base import BaseAdapter
from plyra_guard.core.intent import ActionIntent
from plyra_guard.core.verdict import RiskLevel

if TYPE_CHECKING:
    from plyra_guard.core.guard import ActionGuard

__all__ = ["OpenAIAdapter"]


def _is_openai_tool(tool: Any) -> bool:
    """Check if the object is an OpenAI function call dict."""
    if not isinstance(tool, dict):
        return False
    return tool.get("type") == "function" and "function" in tool


class OpenAIAdapter(BaseAdapter):
    """
    Adapter for OpenAI function call format.

    Handles tool definitions in the format:
    {
        "type": "function",
        "function": {
            "name": "...",
            "description": "...",
            "parameters": {...}
        }
    }
    """

    @property
    def framework_name(self) -> str:
        return "openai"

    def can_handle(self, tool: Any) -> bool:
        return _is_openai_tool(tool)

    def to_intent(
        self, tool: Any, inputs: dict[str, Any], agent_id: str
    ) -> ActionIntent:
        func_def = tool.get("function", {})
        tool_name = func_def.get("name", "unknown")
        description = func_def.get("description", "")

        return ActionIntent(
            action_type=f"openai.{tool_name}",
            tool_name=tool_name,
            parameters=inputs,
            agent_id=agent_id,
            task_context=description,
            risk_level=RiskLevel.MEDIUM,
        )

    def wrap(self, tool: Any, guard: ActionGuard) -> Any:
        """
        For OpenAI tools, wrapping means returning the same dict
        but with a _guard reference attached for runtime interception.
        Since OpenAI tools are just schema dicts and execution is handled
        by the caller, we return a wrapper dict with metadata.
        """
        wrapped = dict(tool)
        wrapped["_plyra_guard"] = {
            "guard": guard,
            "adapter": self,
        }
        return wrapped
