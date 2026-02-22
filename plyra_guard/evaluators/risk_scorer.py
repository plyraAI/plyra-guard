"""
Risk Scorer Evaluator
~~~~~~~~~~~~~~~~~~~~~

Dynamic risk scoring engine that computes a weighted risk score (0.0-1.0)
from multiple signals: action type, parameter sensitivity, blast radius,
agent history, and task context alignment.
"""

from __future__ import annotations

import re
from typing import Any

from plyra_guard.core.intent import ActionIntent, EvaluatorResult
from plyra_guard.core.verdict import Verdict
from plyra_guard.evaluators.base import BaseEvaluator

__all__ = ["RiskScorer"]


# ── Base Risk by Action Type ─────────────────────────────────────────────────

_ACTION_BASE_RISK: dict[str, float] = {
    # Read / GET operations
    "file.read": 0.1,
    "db.select": 0.1,
    "http.get": 0.1,
    "db.query": 0.1,
    # Create / POST operations
    "file.create": 0.3,
    "db.insert": 0.3,
    "http.post": 0.3,
    "email.send": 0.3,
    # Update / PUT operations
    "file.write": 0.5,
    "db.update": 0.5,
    "http.put": 0.5,
    "http.patch": 0.5,
    # Delete / DESTROY operations
    "file.delete": 0.8,
    "db.delete": 0.8,
    "http.delete": 0.8,
    # Shell / Exec
    "shell.exec": 0.9,
    "code.exec": 0.9,
    "system.exec": 0.9,
}

_CATEGORY_BASE_RISK: dict[str, float] = {
    "read": 0.1,
    "get": 0.1,
    "query": 0.1,
    "select": 0.1,
    "create": 0.3,
    "post": 0.3,
    "insert": 0.3,
    "send": 0.3,
    "write": 0.5,
    "update": 0.5,
    "put": 0.5,
    "patch": 0.5,
    "delete": 0.8,
    "destroy": 0.8,
    "remove": 0.8,
    "exec": 0.9,
    "execute": 0.9,
    "shell": 0.9,
    "run": 0.9,
}

# ── Sensitivity Patterns ─────────────────────────────────────────────────────

_SENSITIVE_PATTERNS = [
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
    re.compile(r"private[_-]?key", re.IGNORECASE),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN
    re.compile(r"credit[_-]?card", re.IGNORECASE),
    re.compile(r"\b\d{16}\b"),  # CC number
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}"),  # email
]

_SYSTEM_PATH_PREFIXES = [
    "/etc/",
    "/sys/",
    "/proc/",
    "/boot/",
    "/root/",
    "/var/log/",
    "/usr/sbin/",
    "C:\\Windows\\",
]


class RiskScorer(BaseEvaluator):
    """
    Computes a dynamic risk score (0.0-1.0) for an ActionIntent.

    The score is a weighted combination of:
    1. action_type_base_risk (weight: 0.30)
    2. parameter_sensitivity (weight: 0.25)
    3. blast_radius_estimate (weight: 0.15)
    4. agent_behavior_history (weight: 0.15)
    5. task_context_alignment (weight: 0.15)
    """

    WEIGHT_ACTION_TYPE = 0.30
    WEIGHT_PARAM_SENSITIVITY = 0.25
    WEIGHT_BLAST_RADIUS = 0.15
    WEIGHT_AGENT_HISTORY = 0.15
    WEIGHT_CONTEXT_ALIGNMENT = 0.15

    def __init__(
        self,
        max_risk_score: float = 0.85,
        custom_base_risks: dict[str, float] | None = None,
    ) -> None:
        self._max_risk_score = max_risk_score
        if custom_base_risks:
            _ACTION_BASE_RISK.update(custom_base_risks)

    @property
    def name(self) -> str:
        return "risk_scorer"

    @property
    def priority(self) -> int:
        return 30

    def _score_action_type(self, action_type: str) -> float:
        """Score based on the action type category."""
        if action_type in _ACTION_BASE_RISK:
            return _ACTION_BASE_RISK[action_type]

        # Try to match the verb part
        parts = action_type.lower().split(".")
        for part in reversed(parts):
            if part in _CATEGORY_BASE_RISK:
                return _CATEGORY_BASE_RISK[part]

        return 0.3  # Default medium risk for unknown types

    def _score_parameter_sensitivity(self, params: dict[str, Any]) -> float:
        """Score based on sensitive data in parameters (0.0-0.3)."""
        score = 0.0

        def _scan(value: Any, depth: int = 0) -> float:
            if depth > 5:
                return 0.0
            nonlocal score
            if isinstance(value, str):
                for pattern in _SENSITIVE_PATTERNS:
                    if pattern.search(value):
                        score = min(score + 0.1, 0.3)
                # Check for system paths
                for prefix in _SYSTEM_PATH_PREFIXES:
                    if value.startswith(prefix):
                        score = min(score + 0.15, 0.3)
            elif isinstance(value, dict):
                # Check keys too
                for k, v in value.items():
                    for pattern in _SENSITIVE_PATTERNS:
                        if pattern.search(str(k)):
                            score = min(score + 0.1, 0.3)
                    _scan(v, depth + 1)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    _scan(item, depth + 1)
            return score

        _scan(params)
        return min(score, 0.3)

    def _score_blast_radius(self, intent: ActionIntent) -> float:
        """
        Estimate blast radius (0.0-0.2).

        Considers wildcards, bulk operations, and reversibility.
        """
        score = 0.0
        params = intent.parameters

        # Check for wildcards / bulk indicators
        for value in params.values():
            if isinstance(value, str):
                if "*" in value or "%" in value:
                    score += 0.1
                if value in ("all", "ALL", "*"):
                    score += 0.15
            elif isinstance(value, (list, tuple)) and len(value) > 10:
                score += 0.1

        # Destructive actions have higher blast radius
        if any(
            kw in intent.action_type.lower()
            for kw in ("delete", "destroy", "drop", "truncate")
        ):
            score += 0.1

        return min(score, 0.2)

    def _score_agent_history(self, intent: ActionIntent) -> float:
        """
        Score based on agent behavior history (0.0-0.2).

        Uses metadata injected by the guard at evaluation time.
        """
        meta = intent.metadata
        error_rate = meta.get("agent_error_rate", 0.0)
        violations = meta.get("agent_violations", 0)

        score = error_rate * 0.1 + min(violations * 0.05, 0.1)
        return min(score, 0.2)

    def _score_context_alignment(self, intent: ActionIntent) -> float:
        """
        Score based on action-task alignment (0.0-0.2).

        Uses simple keyword overlap. Returns penalty for misalignment.
        """
        if not intent.task_context:
            return 0.1  # No context = slight penalty

        # Simple keyword overlap between action_type+tool_name and task_context
        action_words = set(
            intent.action_type.lower().replace(".", " ").split()
            + intent.tool_name.lower().replace("_", " ").split()
        )
        context_words = set(intent.task_context.lower().split())

        if not action_words or not context_words:
            return 0.1

        overlap = len(action_words & context_words)
        if overlap > 0:
            return 0.0  # Good alignment
        return 0.1  # Slight penalty for no overlap

    def compute_score(self, intent: ActionIntent) -> float:
        """Compute the final risk score for an ActionIntent."""
        s1 = self._score_action_type(intent.action_type)
        s2 = self._score_parameter_sensitivity(intent.parameters)
        s3 = self._score_blast_radius(intent)
        s4 = self._score_agent_history(intent)
        s5 = self._score_context_alignment(intent)

        raw = (
            s1 * self.WEIGHT_ACTION_TYPE
            + s2 * self.WEIGHT_PARAM_SENSITIVITY
            + s3 * self.WEIGHT_BLAST_RADIUS
            + s4 * self.WEIGHT_AGENT_HISTORY
            + s5 * self.WEIGHT_CONTEXT_ALIGNMENT
        )

        return min(round(raw, 4), 1.0)

    def _score_to_verdict(self, score: float) -> tuple[Verdict, str]:
        """Map a risk score to a verdict."""
        if score >= 0.8:
            return Verdict.BLOCK, "Risk score exceeds critical threshold"
        if score >= 0.6:
            return Verdict.ESCALATE, "Risk score is high — requires approval"
        if score >= 0.3:
            return Verdict.WARN, "Risk score is elevated"
        return Verdict.ALLOW, "Risk score is within acceptable range"

    def evaluate(self, intent: ActionIntent) -> EvaluatorResult:
        """Score the intent and return a risk-based verdict."""
        score = self.compute_score(intent)
        verdict, reason = self._score_to_verdict(score)

        return EvaluatorResult(
            verdict=verdict,
            reason=f"{reason} (score={score:.2f})",
            confidence=0.9,
            evaluator_name=self.name,
            metadata={"risk_score": score},
        )
