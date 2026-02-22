"""
ActionGuard Base Evaluator
~~~~~~~~~~~~~~~~~~~~~~~~~~

Abstract base class for all evaluators in the evaluation pipeline.
Custom evaluators extend this class and implement the evaluate() method.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from plyra_guard.core.intent import ActionIntent, EvaluatorResult

if TYPE_CHECKING:
    pass

__all__ = ["BaseEvaluator"]


class BaseEvaluator(ABC):
    """
    Abstract base class for evaluation pipeline components.

    Each evaluator inspects an ActionIntent and returns an EvaluatorResult
    indicating whether the action should be allowed, blocked, or escalated.

    Subclasses must implement:
        - name: A unique string identifier.
        - evaluate(): The core evaluation logic.

    Optionally override:
        - enabled: To dynamically disable the evaluator.
        - priority: To control ordering (lower runs first).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this evaluator."""
        ...

    @property
    def enabled(self) -> bool:
        """Whether this evaluator is active. Override to disable dynamically."""
        return True

    @property
    def priority(self) -> int:
        """Lower values run first in the pipeline. Default is 100."""
        return 100

    @abstractmethod
    def evaluate(self, intent: ActionIntent) -> EvaluatorResult:
        """
        Evaluate an ActionIntent and return a verdict.

        Args:
            intent: The action to evaluate.

        Returns:
            EvaluatorResult with the verdict and reasoning.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} enabled={self.enabled}>"
