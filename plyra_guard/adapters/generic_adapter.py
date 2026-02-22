"""
Generic Adapter
~~~~~~~~~~~~~~~

Fallback adapter that wraps any Python callable with ActionGuard protection.
"""

from __future__ import annotations

import functools
import inspect
from typing import TYPE_CHECKING, Any

from plyra_guard.adapters.base import BaseAdapter
from plyra_guard.core.intent import ActionIntent
from plyra_guard.core.verdict import RiskLevel

if TYPE_CHECKING:
    from plyra_guard.core.guard import ActionGuard

__all__ = ["GenericAdapter"]


class GenericAdapter(BaseAdapter):
    """
    Fallback adapter for any Python callable.

    This is the ultimate fallback — if no framework-specific adapter matches,
    the generic adapter wraps the callable with ActionGuard protection.
    """

    @property
    def framework_name(self) -> str:
        return "generic"

    def can_handle(self, tool: Any) -> bool:
        """Any callable can be handled by the generic adapter."""
        return callable(tool)

    def to_intent(
        self, tool: Any, inputs: dict[str, Any], agent_id: str
    ) -> ActionIntent:
        """Convert a callable invocation to an ActionIntent."""
        tool_name = getattr(tool, "__name__", str(tool))
        action_type = getattr(tool, "_action_type", f"generic.{tool_name}")

        return ActionIntent(
            action_type=action_type,
            tool_name=tool_name,
            parameters=inputs,
            agent_id=agent_id,
            risk_level=getattr(tool, "_risk_level", RiskLevel.MEDIUM),
        )

    def wrap(self, tool: Any, guard: ActionGuard) -> Any:
        """Wrap a callable with ActionGuard protection."""
        if not callable(tool):
            return tool

        @functools.wraps(tool)
        def _guarded(*args: Any, **kwargs: Any) -> Any:
            # Build parameter dict from args/kwargs
            sig = inspect.signature(tool)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            params = dict(bound.arguments)

            intent = self.to_intent(
                tool,
                params,
                agent_id=getattr(guard, "_default_agent_id", "default"),
            )

            # Use the guard's internal pipeline
            result = guard._execute_guarded(intent, tool, args, kwargs)
            return result

        _guarded._original_tool = tool  # type: ignore[attr-defined]
        _guarded._adapter = self  # type: ignore[attr-defined]
        return _guarded
