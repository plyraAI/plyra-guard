"""
Developer Experience Module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Provides ``explain()``, ``test_policy()``, and ``visualize_pipeline()``
implementations used by ActionGuard.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import yaml

from plyra_guard.core.intent import ActionIntent
from plyra_guard.core.verdict import Verdict
from plyra_guard.evaluators.policy_engine import (
    Policy,
    PolicyEngine,
)
from plyra_guard.exceptions import PolicyConditionError

__all__ = [
    "explain_intent",
    "explain_intent_async",
    "test_policy_snippet",
    "visualize_pipeline",
    "PolicyTestResult",
    "ConditionStep",
]


# ── Verdict Symbols ──────────────────────────────────────────────

_VERDICT_SYMBOL = {
    Verdict.ALLOW: "✅",
    Verdict.WARN: "⚠️",
    Verdict.BLOCK: "🚫",
    Verdict.ESCALATE: "⬆️",
    Verdict.DEFER: "⏳",
}


# ── 1. explain() ─────────────────────────────────────────────────


def explain_intent(guard: Any, intent: ActionIntent) -> str:
    """
    Run the full evaluation pipeline in dry-run mode and return
    a rich, human-readable explanation string.

    This never executes the action.
    """
    from plyra_guard.core.guard import EvaluationPipeline

    pipeline: EvaluationPipeline = guard.pipeline

    # Inject metadata the same way _run_pipeline does
    if guard._trust_ledger.is_registered(intent.agent_id):
        profile = guard._trust_ledger.get(intent.agent_id)
        intent.metadata["agent_error_rate"] = profile.error_rate
        intent.metadata["agent_violations"] = profile.violation_count
        intent.metadata["agent_action_count"] = profile.action_count

    # Run each evaluator with timing
    evaluator_rows: list[str] = []
    final_verdict = Verdict.ALLOW
    final_reason = "No policies triggered"
    blocked_by = None
    triggered_policy = None
    risk_score = 0.0

    for ev in pipeline.evaluators:
        if not ev.enabled:
            evaluator_rows.append(f"  ⏭  {ev.name:<20s} DISABLED")
            continue

        if blocked_by is not None:
            evaluator_rows.append(f"  ⏭  {ev.name:<20s} SKIP   (not reached)")
            continue

        t0 = time.perf_counter()
        try:
            result = ev.evaluate(intent)
        except Exception as exc:
            evaluator_rows.append(f"  ❌ {ev.name:<20s} ERROR  ({exc})")
            continue
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Extract metadata
        if "risk_score" in result.metadata:
            risk_score = result.metadata["risk_score"]
        if "policy_name" in result.metadata:
            triggered_policy = result.metadata["policy_name"]

        if result.verdict == Verdict.BLOCK:
            sym = _VERDICT_SYMBOL[Verdict.BLOCK]
            extra = ""
            if triggered_policy:
                extra = f"  ← triggered: {triggered_policy}"
            evaluator_rows.append(
                f"  {sym} {ev.name:<20s} BLOCK  ({elapsed_ms:.0f}ms){extra}"
            )
            blocked_by = ev.name
            final_verdict = Verdict.BLOCK
            final_reason = result.reason
        elif result.verdict == Verdict.ESCALATE:
            sym = _VERDICT_SYMBOL[Verdict.ESCALATE]
            evaluator_rows.append(
                f"  {sym} {ev.name:<20s} ESCALATE ({elapsed_ms:.0f}ms)"
            )
            if final_verdict not in (Verdict.BLOCK,):
                final_verdict = Verdict.ESCALATE
                final_reason = result.reason
            blocked_by = ev.name
        elif result.verdict == Verdict.DEFER:
            sym = _VERDICT_SYMBOL[Verdict.DEFER]
            evaluator_rows.append(f"  {sym} {ev.name:<20s} DEFER  ({elapsed_ms:.0f}ms)")
            if final_verdict not in (Verdict.BLOCK, Verdict.ESCALATE):
                final_verdict = Verdict.DEFER
                final_reason = result.reason
            blocked_by = ev.name
        elif result.verdict == Verdict.WARN:
            sym = _VERDICT_SYMBOL[Verdict.WARN]
            evaluator_rows.append(f"  {sym} {ev.name:<20s} WARN   ({elapsed_ms:.0f}ms)")
        else:
            evaluator_rows.append(f"  ✅ {ev.name:<20s} PASS   ({elapsed_ms:.0f}ms)")

    # Determine verdict label
    verdict_labels = {
        Verdict.ALLOW: "ALLOWED",
        Verdict.BLOCK: "BLOCKED",
        Verdict.ESCALATE: "ESCALATED",
        Verdict.DEFER: "DEFERRED",
        Verdict.WARN: "WARNED",
    }
    verdict_label = verdict_labels.get(final_verdict, "UNKNOWN")

    # Trust info
    trust_str = "unknown"
    if guard._trust_ledger.is_registered(intent.agent_id):
        profile = guard._trust_ledger.get(intent.agent_id)
        trust_str = f"{profile.trust_level.value}"

    # Format parameters
    try:
        params_str = json.dumps(intent.parameters, indent=2, default=str)
    except Exception:
        params_str = str(intent.parameters)

    sep = "─" * 45
    lines = [
        sep,
        "ACTIONGUARD EXPLANATION",
        sep,
        f"Action:      {intent.action_type} → {intent.tool_name}",
        f"Agent:       {intent.agent_id} (trust: {trust_str})",
        f"Parameters:  {params_str}",
        sep,
        f"VERDICT: {verdict_label}",
        sep,
        "PIPELINE RESULTS:",
        *evaluator_rows,
    ]

    # REASON section
    lines.append("")
    lines.append("REASON:")
    if final_verdict == Verdict.ALLOW:
        lines.append(f"  All evaluators passed. Risk score: {risk_score:.3f}")
    else:
        lines.append(f"  {final_reason}")
        if triggered_policy:
            # Find the policy condition for extra detail
            if hasattr(guard, "_policy_engine"):
                for p in guard._policy_engine.policies:
                    if p.name == triggered_policy:
                        if p.condition:
                            lines.append(f"  Condition: {p.condition}")
                        break

    # HOW TO FIX section
    lines.append("")
    lines.append("HOW TO FIX:")
    if final_verdict == Verdict.BLOCK and triggered_policy:
        lines.append(
            "  Option 1 — Adjust your action parameters to avoid triggering the policy."
        )
        lines.append("  Option 2 — Override this policy in your config:")
        lines.append("             policies:")
        lines.append(f'               - name: "{triggered_policy}"')
        lines.append("                 verdict: WARN   # downgrade from BLOCK")
        lines.append("  Option 3 — Use guard.explain(intent) to debug interactively.")
    elif final_verdict == Verdict.ESCALATE:
        lines.append("  Option 1 — Have a higher-trust agent execute this action.")
        lines.append("  Option 2 — Increase agent trust level in your config.")
        lines.append("  Option 3 — Downgrade the policy verdict from ESCALATE to WARN.")
    elif final_verdict == Verdict.DEFER:
        lines.append("  Option 1 — Retry this action after the deferral period.")
        lines.append("  Option 2 — Remove the deferral policy from your config.")
    elif final_verdict == Verdict.ALLOW:
        lines.append("  No action needed — this action will be allowed.")
    else:
        lines.append("  Review the pipeline results above for details.")

    lines.append(sep)
    return "\n".join(lines)


async def explain_intent_async(guard: Any, intent: ActionIntent) -> str:
    """Async version of explain_intent."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, explain_intent, guard, intent)


# ── 2. test_policy() ────────────────────────────────────────────


@dataclass
class ConditionStep:
    """A single step in condition evaluation trace."""

    expression: str
    value: Any
    result: bool


@dataclass
class PolicyTestResult:
    """Result from interactive policy testing."""

    matched: bool = False
    verdict: Verdict = Verdict.ALLOW
    condition_trace: list[ConditionStep] = field(default_factory=list)
    summary: str = ""
    parse_error: str | None = None
    evaluation_time_ms: float = 0.0


def test_policy_snippet(
    guard: Any,
    yaml_snippet: str,
    sample_intent: ActionIntent,
) -> PolicyTestResult:
    """
    Test a single YAML policy snippet against a sample intent
    without modifying the guard's config.
    """
    result = PolicyTestResult()

    # Parse the YAML
    try:
        parsed = yaml.safe_load(yaml_snippet)
    except yaml.YAMLError as exc:
        result.parse_error = f"YAML parse error: {exc}"
        result.summary = f"Failed to parse YAML: {exc}"
        return result

    if parsed is None:
        result.parse_error = "Empty YAML snippet"
        result.summary = "Empty YAML snippet — nothing to test"
        return result

    # Normalize to a list of dicts
    if isinstance(parsed, dict):
        policy_dicts = [parsed]
    elif isinstance(parsed, list):
        policy_dicts = parsed
    else:
        result.parse_error = f"Expected dict or list, got {type(parsed).__name__}"
        result.summary = "Invalid YAML structure: expected a policy dict or list"
        return result

    # Build a temporary policy engine
    try:
        policies = [Policy.from_dict(d) for d in policy_dicts]
    except Exception as exc:
        result.parse_error = f"Policy parse error: {exc}"
        result.summary = f"Failed to parse policy: {exc}"
        return result

    # Evaluate
    temp_engine = PolicyEngine(policies=policies)
    context = temp_engine._build_context(sample_intent)

    t0 = time.perf_counter()

    for policy in policies:
        if not policy.matches_action_type(sample_intent.action_type):
            expr = (
                f"action_type '{sample_intent.action_type}'"
                f" matches {policy.action_types}"
            )
            result.condition_trace.append(
                ConditionStep(expression=expr, value=False, result=False)
            )
            continue

        expr = (
            f"action_type '{sample_intent.action_type}' matches {policy.action_types}"
        )
        result.condition_trace.append(
            ConditionStep(expression=expr, value=True, result=True)
        )

        if policy.compiled is None:
            result.condition_trace.append(
                ConditionStep(
                    expression="(no condition — always matches)",
                    value=True,
                    result=True,
                )
            )
            result.matched = True
            result.verdict = policy.verdict
            break

        try:
            condition_met = policy.compiled.evaluate(context)
        except PolicyConditionError as exc:
            result.condition_trace.append(
                ConditionStep(
                    expression=policy.condition,
                    value=str(exc),
                    result=False,
                )
            )
            result.parse_error = f"Condition evaluation error: {exc}"
            continue

        result.condition_trace.append(
            ConditionStep(
                expression=policy.condition,
                value=condition_met,
                result=condition_met,
            )
        )

        if condition_met:
            result.matched = True
            result.verdict = policy.verdict
            break

    result.evaluation_time_ms = (time.perf_counter() - t0) * 1000

    # Build summary
    if result.matched:
        result.summary = (
            f"Policy matched: verdict={result.verdict.value}, "
            f"evaluation_time={result.evaluation_time_ms:.2f}ms"
        )
    else:
        result.summary = (
            f"No policy matched for action_type='{sample_intent.action_type}', "
            f"evaluation_time={result.evaluation_time_ms:.2f}ms"
        )

    return result


# ── 3. visualize_pipeline() ──────────────────────────────────────


def visualize_pipeline(guard: Any) -> str:
    """
    Return an ASCII diagram of the current evaluation pipeline.
    """

    config = guard._config

    # Header
    agent_count = len(config.agents)
    policy_count = len(config.policies)
    budget = f"${config.budget.per_task:.2f}/task"
    max_depth = config.global_config.max_delegation_depth
    mode = "strict" if config.global_config.max_risk_score < 0.5 else "standard"

    row1 = (
        f"║  Agents: {agent_count:<3d} │  Policies:"
        f" {policy_count:<3d} │  Budget: {budget:<14s}║"
    )
    row2 = (
        f"║  Max depth: {max_depth:<2d} │  Mode:"
        f" {mode:<8s} │  Version: {config.version:<7s} ║"
    )
    header = [
        "╔══════════════════════════════════════════╗",
        "║       ACTIONGUARD PIPELINE               ║",
        "╠══════════════════════════════════════════╣",
        row1,
        row2,
        "╚══════════════════════════════════════════╝",
        "",
    ]

    # Pipeline boxes
    boxes: list[str] = []
    evaluators = guard.pipeline.evaluators

    for i, ev in enumerate(evaluators):
        idx = i + 1
        enabled_tag = "" if ev.enabled else " (DISABLED)"
        name = ev.name
        label = f"{idx}. {name}{enabled_tag}"

        # Build detail lines
        detail_lines: list[str] = []

        if name == "policy_engine" and hasattr(guard, "_policy_engine"):
            pe = guard._policy_engine
            n = len(pe.policies)
            detail_lines.append(f"  {n} policies loaded")
            for p in pe.policies:
                detail_lines.append(f"  ├─ {p.name:<24s} [{p.verdict.value}]")

        elif name == "risk_scorer" and hasattr(guard, "_risk_scorer"):
            rs = guard._risk_scorer
            threshold = getattr(
                rs, "_max_risk_score", config.global_config.max_risk_score
            )
            detail_lines.append(f"  threshold: {threshold}")

        elif name == "rate_limiter":
            detail_lines.append(f"  default: {config.rate_limits.default}")
            for tool, rate in config.rate_limits.per_tool.items():
                detail_lines.append(f"  {tool}: {rate}")

        elif name == "cost_estimator":
            detail_lines.append(
                f"  per-task: ${config.budget.per_task:.2f} · "
                f"per-agent: ${config.budget.per_agent_per_run:.2f}"
            )

        elif name == "human_gate":
            detail_lines.append(f"  enabled: {ev.enabled}")

        elif name == "schema_validator":
            detail_lines.append("  always runs")

        # Render box
        box_width = 24
        box_top = f"  ┌{'─' * box_width}┐"
        box_title = f"  │ {label:<{box_width - 2}s} │"
        box_details = []
        for dl in detail_lines:
            box_details.append(f"  │ {dl:<{box_width - 2}s} │")
        half = box_width // 2
        tail = box_width - half - 1
        joiner = "┬" if i < len(evaluators) - 1 else "─"
        box_bottom = f"  └{'─' * half}{joiner}{'─' * tail}┘"

        boxes.append(box_top)
        boxes.append(box_title)
        for bd in box_details:
            boxes.append(bd)
        boxes.append(box_bottom)

        if i < len(evaluators) - 1:
            pad = " " * (half + 2)
            boxes.append(f"{pad}│ PASS")

    # Execution gate at the end
    boxes.append(f"  ┌{'─' * 24}┐")
    rollback_status = "enabled" if config.rollback.enabled else "disabled"
    gate_label = "  EXECUTION GATE"
    gate_detail = f"  rollback: {rollback_status}"
    boxes.append(f"  │ {gate_label:<22s} │")
    boxes.append(f"  │ {gate_detail:<22s} │")
    boxes.append(f"  └{'─' * 24}┘")

    # Multi-agent section
    multi_agent = [
        "",
        "MULTI-AGENT:",
    ]
    if config.agents:
        agent_names = [a.id for a in config.agents]
        multi_agent.append(f"  Trust Ledger:  {' → '.join(agent_names)}")
    else:
        multi_agent.append("  Trust Ledger:  (no agents registered)")
    multi_agent.append(
        f"  Cascade limit: depth {max_depth} · "
        f"concurrent {config.global_config.max_concurrent_delegations}"
    )
    budget_str = f"${config.budget.per_task:.2f}"
    multi_agent.append(
        f"  Budget scope:  task-level ({budget_str} shared across agents)"
    )

    return "\n".join(header + boxes + multi_agent)
