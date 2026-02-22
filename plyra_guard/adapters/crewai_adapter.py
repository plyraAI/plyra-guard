"""
CrewAI Adapter
~~~~~~~~~~~~~~

Translates CrewAI BaseTool into ActionIntent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from plyra_guard.adapters.base import BaseAdapter
from plyra_guard.core.intent import ActionIntent
from plyra_guard.core.verdict import RiskLevel

if TYPE_CHECKING:
    from plyra_guard.core.guard import ActionGuard

__all__ = ["CrewAIAdapter"]


def _is_crewai_tool(tool: Any) -> bool:
    """Check if the object is a CrewAI tool."""
    module = getattr(type(tool), "__module__", "") or ""
    return "crewai" in module and hasattr(tool, "_run")


class CrewAIAdapter(BaseAdapter):
    """Adapter for CrewAI BaseTool."""

    @property
    def framework_name(self) -> str:
        return "crewai"

    def can_handle(self, tool: Any) -> bool:
        return _is_crewai_tool(tool)

    def to_intent(
        self, tool: Any, inputs: dict[str, Any], agent_id: str
    ) -> ActionIntent:
        tool_name = getattr(tool, "name", type(tool).__name__)
        description = getattr(tool, "description", "")

        return ActionIntent(
            action_type=f"crewai.{tool_name}",
            tool_name=tool_name,
            parameters=inputs,
            agent_id=agent_id,
            task_context=description,
            risk_level=RiskLevel.MEDIUM,
        )

    def wrap(self, tool: Any, guard: ActionGuard) -> Any:
        adapter = self
        original_run = tool._run

        def _guarded_run(*args: Any, **kwargs: Any) -> Any:
            params = dict(kwargs)
            if args:
                params["_positional_args"] = list(args)
            intent = adapter.to_intent(
                tool,
                params,
                agent_id=getattr(guard, "_default_agent_id", "default"),
            )
            return guard._execute_guarded(intent, original_run, args, kwargs)

        tool._run = _guarded_run
        return tool
