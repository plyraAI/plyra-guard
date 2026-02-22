"""
AutoGen Adapter
~~~~~~~~~~~~~~~

Translates AutoGen tool functions into ActionIntent.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from plyra_guard.adapters.base import BaseAdapter
from plyra_guard.core.intent import ActionIntent
from plyra_guard.core.verdict import RiskLevel

if TYPE_CHECKING:
    from plyra_guard.core.guard import ActionGuard

__all__ = ["AutoGenAdapter"]


def _is_autogen_tool(tool: Any) -> bool:
    """Check if the object is an AutoGen registered tool."""
    module = getattr(type(tool), "__module__", "") or ""
    return (
        "autogen" in module
        or hasattr(tool, "_register_for_execution")
        or (callable(tool) and hasattr(tool, "__wrapped__"))
    )


class AutoGenAdapter(BaseAdapter):
    """Adapter for AutoGen tool functions."""

    @property
    def framework_name(self) -> str:
        return "autogen"

    def can_handle(self, tool: Any) -> bool:
        return _is_autogen_tool(tool)

    def to_intent(
        self, tool: Any, inputs: dict[str, Any], agent_id: str
    ) -> ActionIntent:
        tool_name = getattr(tool, "__name__", str(tool))

        return ActionIntent(
            action_type=f"autogen.{tool_name}",
            tool_name=tool_name,
            parameters=inputs,
            agent_id=agent_id,
            risk_level=RiskLevel.MEDIUM,
        )

    def wrap(self, tool: Any, guard: ActionGuard) -> Any:
        adapter = self

        @functools.wraps(tool)
        def _guarded(*args: Any, **kwargs: Any) -> Any:
            intent = adapter.to_intent(
                tool,
                kwargs,
                agent_id=getattr(guard, "_default_agent_id", "default"),
            )
            return guard._execute_guarded(intent, tool, args, kwargs)

        _guarded._original_tool = tool  # type: ignore[attr-defined]
        return _guarded
