"""
Interceptor
~~~~~~~~~~~~

Intercepts function calls and normalizes them into ActionIntent objects.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from plyra_guard.core.intent import ActionIntent
from plyra_guard.core.verdict import RiskLevel

__all__ = ["Interceptor"]


class Interceptor:
    """
    Intercepts function calls and converts them to ActionIntents.

    Used internally by the ActionGuard.protect() decorator to capture
    function invocations and normalize them before evaluation.
    """

    def __init__(
        self,
        action_type: str,
        risk_level: RiskLevel = RiskLevel.MEDIUM,
        agent_id: str = "default",
        task_id: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        self._action_type = action_type
        self._risk_level = risk_level
        self._agent_id = agent_id
        self._task_id = task_id
        self._tags = tags or []

    def create_intent(
        self,
        func: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> ActionIntent:
        """
        Create an ActionIntent from a function call.

        Args:
            func: The function being called.
            args: Positional arguments.
            kwargs: Keyword arguments.

        Returns:
            A normalized ActionIntent.
        """
        # Build parameter dict from signature
        try:
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            parameters = dict(bound.arguments)
        except (ValueError, TypeError):
            parameters = {"args": list(args), **kwargs}

        tool_name = getattr(func, "__name__", str(func))

        return ActionIntent(
            action_type=self._action_type,
            tool_name=tool_name,
            parameters=parameters,
            agent_id=self._agent_id,
            task_id=self._task_id,
            risk_level=self._risk_level,
            metadata={"tags": self._tags},
        )
