"""
Policy Engine Evaluator
~~~~~~~~~~~~~~~~~~~~~~~

Evaluates ActionIntents against YAML-declared policies with an AST-compiled
condition expression engine for near-zero latency.

Features:
- Nested condition groups: (A and B) or (C and D)
- Policy inheritance: ``extends`` references another policy by name
- Dry-run mode: evaluate ALL policies without short-circuiting
- Conflict detection: warns at startup when policies contradict
- ``in`` membership test support
"""

from __future__ import annotations

import ast
import logging
import operator
import re
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from fnmatch import fnmatch
from typing import Any

from plyra_guard.core.intent import ActionIntent, EvaluatorResult
from plyra_guard.core.verdict import Verdict
from plyra_guard.evaluators.base import BaseEvaluator
from plyra_guard.exceptions import PolicyConditionError, PolicyParseError

__all__ = [
    "PolicyEngine",
    "Policy",
    "CompiledCondition",
    "PolicyDryRunResult",
    "PolicyConflict",
]

logger = logging.getLogger(__name__)


# ── Built-in Functions ───────────────────────────────────────────────────────

_PII_PATTERNS = [
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN
    re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),  # email
    re.compile(r"\b\d{16}\b"),  # credit card (simple)
    re.compile(r"\b\d{3}[-.\\s]?\d{3}[-.\\s]?\d{4}\b"),  # phone
]

_SENSITIVE_PATHS = [
    "/etc",
    "/sys",
    "/proc",
    "/boot",
    "/root",
    "/var/log",
    "/usr/sbin",
    "C:\\Windows\\System32",
]


def _contains_pii(params: dict[str, Any]) -> bool:
    """Check if any parameter value contains PII patterns."""

    def _scan(value: Any) -> bool:
        if isinstance(value, str):
            return any(p.search(value) for p in _PII_PATTERNS)
        if isinstance(value, dict):
            return any(_scan(v) for v in value.values())
        if isinstance(value, (list, tuple)):
            return any(_scan(v) for v in value)
        return False

    return _scan(params)


def _is_sensitive_path(path: str) -> bool:
    """Check if a path is in a sensitive system directory."""
    normalized = path.replace("\\", "/")
    for sp in _SENSITIVE_PATHS:
        sp_normalized = sp.replace("\\", "/")
        if normalized.startswith(sp_normalized):
            return True
    return False


# ── Condition Compiler ───────────────────────────────────────────────────────


_SAFE_OPS: dict[type, Callable[..., Any]] = {
    ast.Gt: operator.gt,
    ast.Lt: operator.lt,
    ast.GtE: operator.ge,
    ast.LtE: operator.le,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.In: lambda a, b: operator.contains(b, a),
    ast.NotIn: lambda a, b: not operator.contains(b, a),
}


@dataclass
class CompiledCondition:
    """A compiled policy condition expression."""

    source: str
    _evaluator: Callable[[dict[str, Any]], bool] | None = field(
        default=None, repr=False
    )

    def evaluate(self, context: dict[str, Any]) -> bool:
        """Evaluate the condition against the given context."""
        if self._evaluator is None:
            self._evaluator = _compile_condition(self.source)
        return self._evaluator(context)


def _compile_condition(source: str) -> Callable[[dict[str, Any]], bool]:
    """
    Compile a condition string into a callable that evaluates
    against a context dict.
    """
    try:
        tree = ast.parse(source, mode="eval")
    except SyntaxError as exc:
        raise PolicyParseError(f"Invalid condition syntax: {source!r}") from exc

    def _eval_node(node: ast.AST, ctx: dict[str, Any]) -> Any:
        if isinstance(node, ast.Expression):
            return _eval_node(node.body, ctx)

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(_eval_node(v, ctx) for v in node.values)
            if isinstance(node.op, ast.Or):
                return any(_eval_node(v, ctx) for v in node.values)

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not _eval_node(node.operand, ctx)

        if isinstance(node, ast.Compare):
            left = _eval_node(node.left, ctx)
            for op_node, comparator in zip(node.ops, node.comparators):
                right = _eval_node(comparator, ctx)
                op_func = _SAFE_OPS.get(type(op_node))
                if op_func is None:
                    raise PolicyConditionError(
                        f"Unsupported operator: {type(op_node).__name__}"
                    )
                if not op_func(left, right):
                    return False
                left = right
            return True

        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Name):
            return _resolve_name(node.id, ctx)

        if isinstance(node, ast.Attribute):
            value = _eval_node(node.value, ctx)
            if isinstance(value, dict):
                return value.get(node.attr, "")
            if value is None:
                return ""
            return getattr(value, node.attr, "")

        if isinstance(node, ast.Call):
            return _eval_call(node, ctx)

        if isinstance(node, ast.List):
            return [_eval_node(e, ctx) for e in node.elts]

        if isinstance(node, ast.Tuple):
            return tuple(_eval_node(e, ctx) for e in node.elts)

        if isinstance(node, ast.Subscript):
            value = _eval_node(node.value, ctx)
            slc = _eval_node(node.slice, ctx)
            try:
                return value[slc]
            except (KeyError, IndexError, TypeError):
                return ""

        if isinstance(node, ast.IfExp):
            test = _eval_node(node.test, ctx)
            return _eval_node(node.body, ctx) if test else _eval_node(node.orelse, ctx)

        raise PolicyConditionError(
            f"Unsupported expression node: {type(node).__name__}"
        )

    def _resolve_name(name: str, ctx: dict[str, Any]) -> Any:
        if name == "True":
            return True
        if name == "False":
            return False
        if name == "None":
            return None
        if name in ctx:
            return ctx[name]
        return ctx.get(name, "")

    def _eval_call(node: ast.Call, ctx: dict[str, Any]) -> Any:
        # Resolve function name
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            # Handle method calls like str.startswith()
            obj = _eval_node(node.func.value, ctx)
            method_name = node.func.attr
            args = [_eval_node(a, ctx) for a in node.args]
            if obj is None:
                return (
                    False
                    if method_name in ("startswith", "endswith", "contains")
                    else ""
                )
            if method_name == "startswith" and isinstance(obj, str):
                return obj.startswith(args[0] if args else "")
            if method_name == "endswith" and isinstance(obj, str):
                return obj.endswith(args[0] if args else "")
            if method_name == "contains" and isinstance(obj, str):
                return (args[0] if args else "") in obj
            if method_name == "lower" and isinstance(obj, str):
                return obj.lower()
            if method_name == "upper" and isinstance(obj, str):
                return obj.upper()
            if method_name == "get" and isinstance(obj, dict):
                key = args[0] if args else ""
                default = args[1] if len(args) > 1 else ""
                return obj.get(key, default)
            if method_name == "keys" and isinstance(obj, dict):
                return list(obj.keys())
            if method_name == "values" and isinstance(obj, dict):
                return list(obj.values())
            raise PolicyConditionError(f"Unsupported method: {method_name}")
        else:
            raise PolicyConditionError("Unsupported function call")

        # Built-in functions
        args = [_eval_node(a, ctx) for a in node.args]
        if func_name == "contains_pii":
            target = args[0] if args else ctx.get("parameters", {})
            return _contains_pii(target if isinstance(target, dict) else {})
        if func_name == "is_sensitive_path":
            return _is_sensitive_path(str(args[0]) if args else "")
        if func_name == "rate_last_5min":
            return ctx.get("_rate_last_5min", 0)
        if func_name == "len":
            return len(args[0]) if args else 0
        if func_name == "str":
            return str(args[0]) if args else ""
        if func_name == "int":
            return int(args[0]) if args else 0
        if func_name == "bool":
            return bool(args[0]) if args else False
        if func_name == "isinstance":
            # Limited isinstance — supports str, int, float, dict, list
            if len(args) >= 2:
                _type_map = {
                    "str": str,
                    "int": int,
                    "float": float,
                    "dict": dict,
                    "list": list,
                }
                type_name = args[1] if isinstance(args[1], str) else ""
                return isinstance(args[0], _type_map.get(type_name, type(None)))
            return False

        raise PolicyConditionError(f"Unknown function: {func_name}")

    def _evaluator(ctx: dict[str, Any]) -> bool:
        try:
            result = _eval_node(tree, ctx)
            return bool(result)
        except PolicyConditionError:
            raise
        except Exception as exc:
            raise PolicyConditionError(f"Condition evaluation error: {exc}") from exc

    return _evaluator


# ── Policy Model ─────────────────────────────────────────────────────────────


_VERDICT_MAP = {
    "BLOCK": Verdict.BLOCK,
    "ESCALATE": Verdict.ESCALATE,
    "DEFER": Verdict.DEFER,
    "WARN": Verdict.WARN,
    "ALLOW_OVERRIDE": Verdict.ALLOW,
    "ALLOW": Verdict.ALLOW,
}

# Verdict severity ordering (lower = more severe)
_VERDICT_SEVERITY = {
    Verdict.BLOCK: 0,
    Verdict.ESCALATE: 1,
    Verdict.DEFER: 2,
    Verdict.WARN: 3,
    Verdict.ALLOW: 4,
}


@dataclass
class Policy:
    """
    A single policy rule loaded from configuration.

    Supports inheritance via ``extends``: the child policy merges
    all fields from the parent, then overrides with its own values.
    """

    name: str
    action_types: list[str]
    condition: str
    verdict: Verdict
    message: str = ""
    escalate_to: str | None = None
    extends: str | None = None
    compiled: CompiledCondition | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.compiled is None and self.condition:
            self.compiled = CompiledCondition(source=self.condition)

    def matches_action_type(self, action_type: str) -> bool:
        """Check if this policy applies to the given action type."""
        for pattern in self.action_types:
            if pattern == "*" or fnmatch(action_type, pattern):
                return True
        return False

    def inherit_from(self, parent: Policy) -> None:
        """
        Inherit unset fields from a parent policy.

        The child keeps any field it has explicitly set;
        fields left at their default values are filled from the parent.
        """
        if not self.action_types or self.action_types == ["*"]:
            self.action_types = list(parent.action_types)
        if not self.condition and parent.condition:
            self.condition = parent.condition
            self.compiled = CompiledCondition(source=self.condition)
        if not self.message and parent.message:
            self.message = parent.message
        if self.escalate_to is None and parent.escalate_to:
            self.escalate_to = parent.escalate_to

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Policy:
        """Create a Policy from a parsed YAML dict."""
        verdict_str = data.get("verdict", "BLOCK")
        verdict = _VERDICT_MAP.get(verdict_str.upper(), Verdict.BLOCK)
        return cls(
            name=data.get("name", "unnamed_policy"),
            action_types=data.get("action_types", ["*"]),
            condition=data.get("condition", ""),
            verdict=verdict,
            message=data.get("message", ""),
            escalate_to=data.get("escalate_to"),
            extends=data.get("extends"),
        )


# ── Dry-run & Conflict Models ───────────────────────────────────────────────


@dataclass
class PolicyDryRunResult:
    """
    Full report from dry-run evaluation of ALL policies.

    Unlike normal evaluation, dry-run does NOT short-circuit on BLOCK.
    Every policy is evaluated and its result recorded.
    """

    intent: ActionIntent
    results: list[dict[str, Any]] = field(default_factory=list)
    triggered_policies: list[str] = field(default_factory=list)
    worst_verdict: Verdict = Verdict.ALLOW

    @property
    def would_block(self) -> bool:
        """Whether any triggered policy would block."""
        return self.worst_verdict == Verdict.BLOCK

    @property
    def summary(self) -> str:
        triggered = len(self.triggered_policies)
        total = len(self.results)
        return (
            f"{triggered}/{total} policies triggered, "
            f"worst verdict: {self.worst_verdict.value}"
        )


@dataclass
class PolicyConflict:
    """
    Describes a potential conflict between two policies.

    A conflict exists when two policies can match the same action type
    but produce contradicting verdicts (e.g., BLOCK vs ALLOW).
    """

    policy_a: str
    policy_b: str
    overlapping_types: list[str]
    verdict_a: Verdict
    verdict_b: Verdict
    message: str = ""

    def __str__(self) -> str:
        return (
            f"Conflict: '{self.policy_a}' ({self.verdict_a.value}) vs "
            f"'{self.policy_b}' ({self.verdict_b.value}) on "
            f"{self.overlapping_types}"
        )


# ── Policy Engine Evaluator ──────────────────────────────────────────────────


class PolicyEngine(BaseEvaluator):
    """
    Evaluates ActionIntents against a set of YAML-declared policies.

    Policies are compiled into AST at initialization for near-zero
    evaluation latency at runtime.
    """

    def __init__(self, policies: list[Policy] | None = None) -> None:
        self._policies: list[Policy] = policies or []

    @property
    def name(self) -> str:
        return "policy_engine"

    @property
    def priority(self) -> int:
        return 20

    @property
    def policies(self) -> list[Policy]:
        """Return the list of loaded policies."""
        return self._policies

    def load_policies(self, policy_dicts: list[dict[str, Any]]) -> None:
        """
        Load policies from a list of parsed YAML dicts.

        Resolves ``extends`` references after all policies are loaded.
        Runs conflict detection and emits warnings.
        """
        self._policies = [Policy.from_dict(d) for d in policy_dicts]
        self._resolve_inheritance()
        conflicts = self.detect_conflicts()
        for conflict in conflicts:
            warnings.warn(str(conflict), stacklevel=2)

    def add_policy(self, policy: Policy) -> None:
        """Add a single policy to the engine."""
        if policy.extends:
            parent = self._find_policy(policy.extends)
            if parent:
                policy.inherit_from(parent)
        self._policies.append(policy)

    def _find_policy(self, name: str) -> Policy | None:
        """Lookup a policy by name."""
        for p in self._policies:
            if p.name == name:
                return p
        return None

    def _resolve_inheritance(self) -> None:
        """Resolve ``extends`` references across all loaded policies."""
        by_name = {p.name: p for p in self._policies}
        for policy in self._policies:
            if policy.extends and policy.extends in by_name:
                policy.inherit_from(by_name[policy.extends])

    # ── Conflict Detection ────────────────────────────────────────

    def detect_conflicts(self) -> list[PolicyConflict]:
        """
        Detect potential conflicts between loaded policies.

        Two policies conflict when:
        1. They can match the same action type (overlapping globs).
        2. They have contradicting verdicts (BLOCK vs ALLOW, etc.).

        Returns a list of PolicyConflict objects.
        """
        conflicts: list[PolicyConflict] = []
        n = len(self._policies)

        for i in range(n):
            for j in range(i + 1, n):
                a = self._policies[i]
                b = self._policies[j]

                # Same verdict → no conflict
                if a.verdict == b.verdict:
                    continue

                # Check for overlapping action types
                overlapping = self._find_overlapping_types(
                    a.action_types, b.action_types
                )
                if not overlapping:
                    continue

                # Check if verdicts are contradicting
                sev_a = _VERDICT_SEVERITY.get(a.verdict, 5)
                sev_b = _VERDICT_SEVERITY.get(b.verdict, 5)
                if abs(sev_a - sev_b) >= 2:  # 2+ levels apart = conflict
                    conflicts.append(
                        PolicyConflict(
                            policy_a=a.name,
                            policy_b=b.name,
                            overlapping_types=overlapping,
                            verdict_a=a.verdict,
                            verdict_b=b.verdict,
                            message=(
                                f"Policies '{a.name}' and '{b.name}' have "
                                f"contradicting verdicts on {overlapping}"
                            ),
                        )
                    )

        return conflicts

    @staticmethod
    def _find_overlapping_types(types_a: list[str], types_b: list[str]) -> list[str]:
        """Find action type patterns that could overlap."""
        overlapping: list[str] = []
        for a_pat in types_a:
            for b_pat in types_b:
                if a_pat == "*" or b_pat == "*":
                    overlapping.append(f"{a_pat} ∩ {b_pat}")
                elif a_pat == b_pat:
                    overlapping.append(a_pat)
                elif fnmatch(a_pat, b_pat) or fnmatch(b_pat, a_pat):
                    overlapping.append(f"{a_pat} ∩ {b_pat}")
        return overlapping

    # ── Context Building ──────────────────────────────────────────

    def _build_context(self, intent: ActionIntent) -> dict[str, Any]:
        """Build the evaluation context from an ActionIntent."""
        chain_trust = 1.0
        if intent.instruction_chain:
            chain_trust = min(ac.trust_level for ac in intent.instruction_chain)

        return {
            "parameters": intent.parameters,
            "estimated_cost": intent.estimated_cost,
            "risk_level": intent.risk_level.value,
            "action_type": intent.action_type,
            "agent": {
                "id": intent.agent_id,
                "trust_level": chain_trust,
                "action_count": intent.metadata.get("agent_action_count", 0),
            },
            "task": {
                "id": intent.task_id,
                "estimated_cost": intent.metadata.get("task_estimated_cost", 0.0),
            },
        }

    # ── Evaluation ────────────────────────────────────────────────

    def evaluate(self, intent: ActionIntent) -> EvaluatorResult:
        """Evaluate the intent against all loaded policies."""
        context = self._build_context(intent)

        for policy in self._policies:
            if not policy.matches_action_type(intent.action_type):
                continue

            if policy.compiled is None:
                continue

            try:
                if policy.compiled.evaluate(context):
                    return EvaluatorResult(
                        verdict=policy.verdict,
                        reason=policy.message or f"Policy '{policy.name}' triggered",
                        confidence=1.0,
                        evaluator_name=self.name,
                        metadata={
                            "policy_name": policy.name,
                            "escalate_to": policy.escalate_to,
                        },
                    )
            except PolicyConditionError:
                # Log but don't block on condition evaluation errors
                continue

        return EvaluatorResult(
            verdict=Verdict.ALLOW,
            reason="No policies triggered",
            confidence=1.0,
            evaluator_name=self.name,
        )

    # ── Dry-Run Mode ──────────────────────────────────────────────

    def dry_run(self, intent: ActionIntent) -> PolicyDryRunResult:
        """
        Evaluate ALL policies without blocking. Returns a full report.

        Unlike ``evaluate()``, this does NOT short-circuit on BLOCK.
        Every policy is evaluated and its result is recorded.
        """
        context = self._build_context(intent)
        result = PolicyDryRunResult(intent=intent)
        worst_severity = 99

        for policy in self._policies:
            matched_type = policy.matches_action_type(intent.action_type)
            condition_met = False
            error_msg = None

            if matched_type and policy.compiled is not None:
                try:
                    condition_met = policy.compiled.evaluate(context)
                except PolicyConditionError as exc:
                    error_msg = str(exc)

            triggered = matched_type and condition_met

            entry = {
                "policy_name": policy.name,
                "action_type_matched": matched_type,
                "condition_met": condition_met,
                "triggered": triggered,
                "verdict": policy.verdict.value,
                "message": policy.message,
                "error": error_msg,
            }
            result.results.append(entry)

            if triggered:
                result.triggered_policies.append(policy.name)
                sev = _VERDICT_SEVERITY.get(policy.verdict, 99)
                if sev < worst_severity:
                    worst_severity = sev
                    result.worst_verdict = policy.verdict

        return result
