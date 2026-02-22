"""
Anthropic Adapter
~~~~~~~~~~~~~~~~~

Translates Anthropic tool_use block dicts into ActionIntent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from plyra_guard.adapters.base import BaseAdapter
from plyra_guard.core.intent import ActionIntent
from plyra_guard.core.verdict import RiskLevel

if TYPE_CHECKING:
    from plyra_guard.core.guard import ActionGuard

__all__ = ["AnthropicAdapter"]


def _is_anthropic_tool(tool: Any) -> bool:
    """Check if the object is an Anthropic tool definition dict."""
    if not isinstance(tool, dict):
        return False
    return "name" in tool and "input_schema" in tool


class AnthropicAdapter(BaseAdapter):
    """
    Adapter for Anthropic tool_use format.

    Handles tool definitions in the format:
    {
        "name": "...",
        "description": "...",
        "input_schema": {...}
    }
    """

    @property
    def framework_name(self) -> str:
        return "anthropic"

    def can_handle(self, tool: Any) -> bool:
        return _is_anthropic_tool(tool)

    def to_intent(
        self, tool: Any, inputs: dict[str, Any], agent_id: str
    ) -> ActionIntent:
        tool_name = tool.get("name", "unknown")
        description = tool.get("description", "")

        return ActionIntent(
            action_type=f"anthropic.{tool_name}",
            tool_name=tool_name,
            parameters=inputs,
            agent_id=agent_id,
            task_context=description,
            risk_level=RiskLevel.MEDIUM,
        )

    def wrap(self, tool: Any, guard: ActionGuard) -> Any:
        """
        For Anthropic tools (dict schemas), attach guard metadata
        for runtime interception.
        """
        wrapped = dict(tool)
        wrapped["_plyra_guard"] = {
            "guard": guard,
            "adapter": self,
        }
        return wrapped
