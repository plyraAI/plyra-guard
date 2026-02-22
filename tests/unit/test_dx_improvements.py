"""
Developer Experience Improvements Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

20 tests covering:
- guard.explain() (6 tests)
- guard.test_policy() (5 tests)
- Improved error messages (5 tests)
- guard.visualize_pipeline() (4 tests)
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

import pytest

from plyra_guard import ActionGuard, ActionIntent, Verdict
from plyra_guard.config.loader import load_config_from_dict
from plyra_guard.core.dx import ConditionStep, PolicyTestResult
from plyra_guard.exceptions import (
    ActionEscalatedError,
    BudgetExceededError,
    ExecutionBlockedError,
    RateLimitExceededError,
    TrustViolationError,
)

# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def guard_with_policies() -> ActionGuard:
    """Guard configured with blocking and escalation policies."""
    config = load_config_from_dict(
        {
            "policies": [
                {
                    "name": "block_system_paths",
                    "action_types": ["file.delete", "file.write", "file.read"],
                    "condition": "parameters.path.startswith('/etc') or parameters.path.startswith('/sys')",
                    "verdict": "BLOCK",
                    "message": "System path access is forbidden",
                },
                {
                    "name": "escalate_high_cost",
                    "action_types": ["*"],
                    "condition": "estimated_cost > 0.50",
                    "verdict": "ESCALATE",
                    "message": "Action cost exceeds $0.50 threshold",
                },
                {
                    "name": "warn_low_trust",
                    "action_types": ["email.send"],
                    "condition": "agent.trust_level < 0.5",
                    "verdict": "WARN",
                    "message": "Low trust agent sending email",
                },
            ],
        }
    )
    guard = ActionGuard(config=config)
    guard._audit_log._exporters.clear()
    return guard


def _make_intent(**kw) -> ActionIntent:
    defaults = {
        "action_type": "file.read",
        "tool_name": "test_tool",
        "parameters": {},
        "agent_id": "test-agent",
    }
    defaults.update(kw)
    return ActionIntent(**defaults)


# ══════════════════════════════════════════════════════════════════
# 1. guard.explain() — 6 tests
# ══════════════════════════════════════════════════════════════════


class TestExplain:
    """Tests for guard.explain() method."""

    def test_explain_blocked_action(self, guard_with_policies):
        """explain() shows BLOCKED verdict with policy name."""
        intent = _make_intent(
            action_type="file.delete",
            tool_name="delete_file",
            parameters={"path": "/etc/hosts"},
        )
        output = guard_with_policies.explain(intent)

        assert "VERDICT: BLOCKED" in output
        assert "block_system_paths" in output
        assert "file.delete" in output
        assert "PIPELINE RESULTS:" in output
        assert "HOW TO FIX:" in output
        assert "REASON:" in output

    def test_explain_allowed_action(self, guard_with_policies):
        """explain() shows ALLOWED verdict with risk score."""
        intent = _make_intent(
            action_type="file.read",
            tool_name="read_file",
            parameters={"path": "/tmp/safe.txt"},
        )
        output = guard_with_policies.explain(intent)

        assert "VERDICT: ALLOWED" in output
        assert "PASS" in output
        assert "No action needed" in output

    def test_explain_escalated_action(self, guard_with_policies):
        """explain() shows ESCALATED verdict."""
        intent = _make_intent(
            action_type="http.post",
            tool_name="api_call",
            parameters={"url": "https://expensive-api.com"},
            estimated_cost=5.00,
        )
        output = guard_with_policies.explain(intent)

        assert "VERDICT: ESCALATED" in output
        assert "cost" in output.lower() or "ESCALATE" in output

    def test_explain_shows_all_evaluators(self, guard_with_policies):
        """explain() includes every evaluator in the pipeline."""
        intent = _make_intent(
            action_type="file.read",
            parameters={"path": "/tmp/test.txt"},
        )
        output = guard_with_policies.explain(intent)

        # All default evaluators should appear
        assert "schema_validator" in output
        assert "policy_engine" in output
        assert "risk_scorer" in output

    def test_explain_async_version(self, guard_with_policies):
        """explain_async returns the same content as explain."""
        intent = _make_intent(
            action_type="file.read",
            parameters={"path": "/tmp/test.txt"},
        )
        sync_output = guard_with_policies.explain(intent)
        async_output = asyncio.get_event_loop().run_until_complete(
            guard_with_policies.explain_async(intent)
        )

        # Both should contain the same verdict
        assert "VERDICT:" in sync_output
        assert "VERDICT:" in async_output
        # Both should have the same verdict
        assert ("ALLOWED" in sync_output) == ("ALLOWED" in async_output)

    def test_explain_cli_command(self):
        """The explain CLI subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, "-m", "plyra_guard", "explain", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--action" in result.stdout
        assert "--params" in result.stdout


# ══════════════════════════════════════════════════════════════════
# 2. guard.test_policy() — 5 tests
# ══════════════════════════════════════════════════════════════════


class TestTestPolicy:
    """Tests for guard.test_policy() method."""

    def test_test_policy_matching_condition(self, guard_with_policies):
        """test_policy returns matched=True when condition matches."""
        result = guard_with_policies.test_policy(
            yaml_snippet="""
            - name: "test_my_policy"
              action_types: ["file.delete"]
              condition: "parameters.path.startswith('/etc')"
              verdict: BLOCK
            """,
            sample_intent=_make_intent(
                action_type="file.delete",
                parameters={"path": "/etc/hosts"},
            ),
        )

        assert isinstance(result, PolicyTestResult)
        assert result.matched is True
        assert result.verdict == Verdict.BLOCK
        assert result.parse_error is None
        assert result.evaluation_time_ms >= 0

    def test_test_policy_non_matching_condition(self, guard_with_policies):
        """test_policy returns matched=False when condition doesn't match."""
        result = guard_with_policies.test_policy(
            yaml_snippet="""
            - name: "test_policy"
              action_types: ["file.delete"]
              condition: "parameters.path.startswith('/etc')"
              verdict: BLOCK
            """,
            sample_intent=_make_intent(
                action_type="file.delete",
                parameters={"path": "/home/user/file.txt"},
            ),
        )

        assert result.matched is False
        assert result.verdict == Verdict.ALLOW  # default when not matched

    def test_test_policy_invalid_yaml_returns_parse_error(self, guard_with_policies):
        """test_policy returns parse_error for invalid YAML."""
        result = guard_with_policies.test_policy(
            yaml_snippet="{ invalid: yaml: [broken",
            sample_intent=_make_intent(),
        )

        assert result.parse_error is not None
        assert "parse" in result.parse_error.lower() or "YAML" in result.parse_error

    def test_test_policy_condition_trace_contents(self, guard_with_policies):
        """test_policy includes condition trace steps."""
        result = guard_with_policies.test_policy(
            yaml_snippet="""
            - name: "traced_policy"
              action_types: ["file.delete"]
              condition: "parameters.path.startswith('/etc')"
              verdict: BLOCK
            """,
            sample_intent=_make_intent(
                action_type="file.delete",
                parameters={"path": "/etc/hosts"},
            ),
        )

        assert len(result.condition_trace) >= 1
        # Should have at least the action_type match and condition evaluation
        assert any(step.result for step in result.condition_trace)
        # Each step has all required fields
        for step in result.condition_trace:
            assert isinstance(step, ConditionStep)
            assert isinstance(step.expression, str)
            assert isinstance(step.result, bool)

    def test_test_policy_cli_command(self):
        """The test-policy CLI subcommand is recognized."""
        result = subprocess.run(
            [sys.executable, "-m", "plyra_guard", "test-policy", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "--condition" in result.stdout
        assert "--action-type" in result.stdout


# ══════════════════════════════════════════════════════════════════
# 3. Improved Error Messages — 5 tests
# ══════════════════════════════════════════════════════════════════


class TestImprovedErrors:
    """Tests for structured error messages."""

    def test_blocked_error_has_three_fields(self):
        """ExecutionBlockedError has what_happened, policy_triggered, how_to_fix."""
        err = ExecutionBlockedError(
            message="Action blocked by PolicyEngine",
            verdict="BLOCK",
            reason='Policy "block_system_paths" matched',
            what_happened='The action "file.delete" was blocked by policy "block_system_paths".',
            policy_triggered="block_system_paths",
            how_to_fix="1. Use a path outside /etc\n2. Downgrade the policy verdict to WARN",
        )

        assert hasattr(err, "what_happened")
        assert hasattr(err, "policy_triggered")
        assert hasattr(err, "how_to_fix")
        assert "file.delete" in err.what_happened
        assert "block_system_paths" in err.policy_triggered
        assert "WARN" in err.how_to_fix

        # __str__ should render structured output
        s = str(err)
        assert "What happened:" in s
        assert "Policy triggered:" in s
        assert "How to fix:" in s

    def test_escalated_error_has_three_fields(self):
        """ActionEscalatedError has structured fields."""
        err = ActionEscalatedError(
            message="Action requires human approval",
            reason="Cost exceeds threshold",
            escalate_to="human",
            policy_triggered="escalate_high_cost",
        )

        assert hasattr(err, "what_happened")
        assert "human" in err.what_happened
        assert err.policy_triggered == "escalate_high_cost"
        assert "trust" in err.how_to_fix.lower() or "escalat" in err.how_to_fix.lower()

        s = str(err)
        assert "What happened:" in s
        assert "How to fix:" in s

    def test_rate_limit_error_message_is_actionable(self):
        """RateLimitExceededError provides actionable fix steps."""
        err = RateLimitExceededError(
            message="Rate limit exceeded",
            agent_id="agent-1",
            tool_name="send_email",
            limit="5/min",
        )

        assert "agent-1" in err.what_happened
        assert "send_email" in err.what_happened
        assert "rate_limiter" in err.policy_triggered

        s = str(err)
        assert "How to fix:" in s
        assert "send_email" in s

    def test_budget_error_message_is_actionable(self):
        """BudgetExceededError provides actionable fix steps."""
        err = BudgetExceededError(
            message="Budget exceeded",
            current_spend=4.50,
            budget_limit=5.00,
        )

        assert "$4.50" in err.what_happened
        assert "$5.00" in err.what_happened
        assert "cost_estimator" in err.policy_triggered

        s = str(err)
        assert "How to fix:" in s
        assert "budget" in s.lower()

    def test_trust_violation_error_message_is_actionable(self):
        """TrustViolationError provides actionable fix steps."""
        err = TrustViolationError(
            message="Trust violation",
            agent_id="sub-agent-1",
            required_trust="ORCHESTRATOR",
            actual_trust="SUB_AGENT",
        )

        assert "sub-agent-1" in err.what_happened
        assert "trust_ledger" in err.policy_triggered
        assert "trust" in err.how_to_fix.lower()

        s = str(err)
        assert "What happened:" in s
        assert "How to fix:" in s


# ══════════════════════════════════════════════════════════════════
# 4. guard.visualize_pipeline() — 4 tests
# ══════════════════════════════════════════════════════════════════


class TestVisualizePipeline:
    """Tests for guard.visualize_pipeline() method."""

    def test_visualize_returns_string(self, guard_with_policies):
        """visualize_pipeline() returns a non-empty string."""
        output = guard_with_policies.visualize_pipeline()

        assert isinstance(output, str)
        assert len(output) > 100

    def test_visualize_contains_all_evaluators(self, guard_with_policies):
        """visualize_pipeline() lists all evaluators in the pipeline."""
        output = guard_with_policies.visualize_pipeline()

        # All default evaluators should appear
        assert "schema_validator" in output
        assert "policy_engine" in output
        assert "risk_scorer" in output
        assert "rate_limiter" in output
        assert "cost_estimator" in output

    def test_visualize_shows_policy_names(self, guard_with_policies):
        """visualize_pipeline() includes policy names in the output."""
        output = guard_with_policies.visualize_pipeline()

        assert "block_system_paths" in output
        assert "escalate_high_cost" in output
        assert "warn_low_trust" in output

    def test_str_repr_calls_visualize(self, guard_with_policies):
        """str(guard) and repr(guard) return the pipeline visualization."""
        viz = guard_with_policies.visualize_pipeline()
        str_output = str(guard_with_policies)
        repr_output = repr(guard_with_policies)

        # All three should contain the pipeline header
        assert "ACTIONGUARD PIPELINE" in viz
        assert "ACTIONGUARD PIPELINE" in str_output
        assert "ACTIONGUARD PIPELINE" in repr_output


# ══════════════════════════════════════════════════════════════════
# 5. guard.evaluate_async() — 2 tests
# ══════════════════════════════════════════════════════════════════


class TestEvaluateAsync:
    """Tests for guard.evaluate_async() method."""

    @pytest.mark.asyncio
    async def test_evaluate_async_returns_evaluator_result(self):
        """evaluate_async() returns an EvaluatorResult."""
        from plyra_guard.core.intent import EvaluatorResult

        guard = ActionGuard.default()
        intent = _make_intent(action_type="file.read")
        result = await guard.evaluate_async(intent)
        assert isinstance(result, EvaluatorResult)
        assert result.verdict in list(Verdict)

    @pytest.mark.asyncio
    async def test_evaluate_async_matches_sync_verdict(self):
        """evaluate_async() produces the same verdict as evaluate()."""
        guard = ActionGuard.default()
        intent = _make_intent(action_type="file.read")
        sync_result = guard.evaluate(intent)
        async_result = await guard.evaluate_async(intent)
        assert sync_result.verdict == async_result.verdict
