"""
Extended Policy Engine Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

20+ edge-case unit tests covering:
- Nested condition groups
- Policy inheritance
- Dry-run mode
- Conflict detection
- Empty parameters, None values, deeply nested paths
- Unicode in strings, extremely long strings
- ``in`` / ``not in`` membership tests
"""

from __future__ import annotations

import warnings

import pytest

from plyra_guard import ActionIntent, Verdict
from plyra_guard.evaluators.policy_engine import (
    CompiledCondition,
    Policy,
    PolicyConflict,
    PolicyDryRunResult,
    PolicyEngine,
)
from plyra_guard.exceptions import PolicyConditionError, PolicyParseError

# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def engine() -> PolicyEngine:
    """Engine with a variety of test policies (no conflict detection)."""
    pe = PolicyEngine()
    pe._policies = [
        Policy.from_dict(d)
        for d in [
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
        ]
    ]
    pe._resolve_inheritance()
    return pe


def _make_intent(**kw) -> ActionIntent:
    """Shortcut to create an ActionIntent."""
    defaults = {
        "action_type": "file.read",
        "tool_name": "test_tool",
        "parameters": {},
        "agent_id": "agent-1",
    }
    defaults.update(kw)
    return ActionIntent(**defaults)


# ── 1. Nested Condition Groups ───────────────────────────────────


class TestNestedConditions:
    """Tests for (A and B) or (C and D) nested groups."""

    def test_and_group_both_true(self):
        cc = CompiledCondition(
            source="(estimated_cost > 0.1) and (risk_level == 'HIGH')"
        )
        ctx = {"estimated_cost": 0.5, "risk_level": "HIGH", "parameters": {}}
        assert cc.evaluate(ctx) is True

    def test_and_group_one_false(self):
        cc = CompiledCondition(
            source="(estimated_cost > 0.1) and (risk_level == 'HIGH')"
        )
        ctx = {"estimated_cost": 0.5, "risk_level": "LOW", "parameters": {}}
        assert cc.evaluate(ctx) is False

    def test_or_group(self):
        cc = CompiledCondition(
            source="(estimated_cost > 10) or (risk_level == 'CRITICAL')"
        )
        ctx = {"estimated_cost": 0.01, "risk_level": "CRITICAL", "parameters": {}}
        assert cc.evaluate(ctx) is True

    def test_nested_and_or(self):
        """(A and B) or (C and D) — only second group true."""
        cc = CompiledCondition(
            source="(estimated_cost > 10 and risk_level == 'LOW') or "
            "(estimated_cost < 1 and risk_level == 'HIGH')"
        )
        ctx = {"estimated_cost": 0.5, "risk_level": "HIGH", "parameters": {}}
        assert cc.evaluate(ctx) is True

    def test_deeply_nested_groups(self):
        """((A or B) and (C or D)) — all layers."""
        cc = CompiledCondition(
            source="((estimated_cost > 0 or risk_level == 'X') and "
            "(action_type == 'file.read' or action_type == 'file.write'))"
        )
        ctx = {
            "estimated_cost": 1.0,
            "risk_level": "LOW",
            "action_type": "file.read",
            "parameters": {},
        }
        assert cc.evaluate(ctx) is True

    def test_not_nested(self):
        """not (A and B)"""
        cc = CompiledCondition(
            source="not (estimated_cost > 10 and risk_level == 'HIGH')"
        )
        ctx = {"estimated_cost": 0.1, "risk_level": "LOW", "parameters": {}}
        assert cc.evaluate(ctx) is True


# ── 2. Policy Inheritance ────────────────────────────────────────


class TestPolicyInheritance:
    """Tests for policy ``extends`` (child inherits parent fields)."""

    def test_child_inherits_condition(self):
        """Child with no condition inherits parent's condition."""
        pe = PolicyEngine()
        pe.load_policies(
            [
                {
                    "name": "base_cost_policy",
                    "action_types": ["*"],
                    "condition": "estimated_cost > 1.00",
                    "verdict": "BLOCK",
                    "message": "Cost too high",
                },
                {
                    "name": "strict_cost_for_email",
                    "action_types": ["email.send"],
                    "condition": "",  # empty → inherits
                    "verdict": "BLOCK",
                    "extends": "base_cost_policy",
                },
            ]
        )

        child = pe._find_policy("strict_cost_for_email")
        assert child is not None
        assert child.condition == "estimated_cost > 1.00"
        assert child.action_types == ["email.send"]  # kept its own

    def test_child_overrides_verdict(self):
        """Child keeps its own verdict even when extending."""
        pe = PolicyEngine()
        pe.load_policies(
            [
                {
                    "name": "parent",
                    "action_types": ["*"],
                    "condition": "estimated_cost > 1",
                    "verdict": "BLOCK",
                    "message": "Blocked by parent",
                },
                {
                    "name": "child_warn",
                    "action_types": ["*"],
                    "condition": "estimated_cost > 1",
                    "verdict": "WARN",
                    "extends": "parent",
                    "message": "Warning from child",
                },
            ]
        )

        child = pe._find_policy("child_warn")
        assert child is not None
        assert child.verdict == Verdict.WARN
        assert child.message == "Warning from child"

    def test_child_inherits_action_types_when_wildcard(self):
        """Child with default ["*"] inherits parent's action_types."""
        pe = PolicyEngine()
        pe.load_policies(
            [
                {
                    "name": "parent_specific",
                    "action_types": ["file.delete", "file.write"],
                    "condition": "estimated_cost > 0",
                    "verdict": "BLOCK",
                },
                {
                    "name": "child_inherits_types",
                    "action_types": ["*"],
                    "condition": "estimated_cost > 0",
                    "verdict": "WARN",
                    "extends": "parent_specific",
                },
            ]
        )

        child = pe._find_policy("child_inherits_types")
        assert child is not None
        assert child.action_types == ["file.delete", "file.write"]

    def test_nonexistent_parent_ignored(self):
        """Extending a non-existent parent doesn't crash."""
        pe = PolicyEngine()
        pe.load_policies(
            [
                {
                    "name": "orphan",
                    "action_types": ["*"],
                    "condition": "estimated_cost > 0",
                    "verdict": "BLOCK",
                    "extends": "does_not_exist",
                },
            ]
        )

        orphan = pe._find_policy("orphan")
        assert orphan is not None
        # Still functional
        intent = _make_intent(estimated_cost=5.0)
        result = pe.evaluate(intent)
        assert result.verdict == Verdict.BLOCK


# ── 3. Dry-Run Mode ─────────────────────────────────────────────


class TestDryRunMode:
    """Tests for dry-run evaluation (no short-circuiting)."""

    def test_dry_run_evaluates_all_policies(self, engine):
        """Dry-run returns results for every policy, not just the first match."""
        intent = _make_intent(
            action_type="file.read",
            parameters={"path": "/etc/passwd"},
            estimated_cost=2.00,
        )
        report = engine.dry_run(intent)

        assert isinstance(report, PolicyDryRunResult)
        assert len(report.results) == len(engine.policies)

    def test_dry_run_records_triggered(self, engine):
        """Dry-run records which policies were triggered."""
        intent = _make_intent(
            action_type="file.read",
            parameters={"path": "/etc/passwd"},
            estimated_cost=2.00,
        )
        report = engine.dry_run(intent)

        assert "block_system_paths" in report.triggered_policies
        assert "escalate_high_cost" in report.triggered_policies
        assert report.worst_verdict == Verdict.BLOCK
        assert report.would_block is True

    def test_dry_run_no_triggers(self, engine):
        """Dry-run with no triggers → ALLOW, empty list."""
        intent = _make_intent(
            action_type="http.get",
            parameters={"url": "https://safe.com"},
            estimated_cost=0.01,
        )
        report = engine.dry_run(intent)

        assert len(report.triggered_policies) == 0
        assert report.worst_verdict == Verdict.ALLOW
        assert report.would_block is False

    def test_dry_run_summary(self, engine):
        """Dry-run summary is a human-readable string."""
        intent = _make_intent(
            action_type="file.delete",
            parameters={"path": "/etc/hosts"},
        )
        report = engine.dry_run(intent)
        assert "policies triggered" in report.summary
        assert "worst verdict" in report.summary


# ── 4. Conflict Detection ───────────────────────────────────────


class TestConflictDetection:
    """Tests for startup policy conflict warnings."""

    def test_detects_block_vs_allow_conflict(self):
        """Two policies on same type with BLOCK vs ALLOW = conflict."""
        pe = PolicyEngine()
        pe._policies = [
            Policy.from_dict(
                {
                    "name": "block_all",
                    "action_types": ["file.delete"],
                    "condition": "estimated_cost > 0",
                    "verdict": "BLOCK",
                }
            ),
            Policy.from_dict(
                {
                    "name": "allow_all",
                    "action_types": ["file.delete"],
                    "condition": "estimated_cost > 0",
                    "verdict": "ALLOW",
                }
            ),
        ]

        conflicts = pe.detect_conflicts()
        assert len(conflicts) == 1
        assert conflicts[0].policy_a == "block_all"
        assert conflicts[0].policy_b == "allow_all"

    def test_no_conflict_same_verdict(self):
        """Same verdict = no conflict, even on same type."""
        pe = PolicyEngine()
        pe._policies = [
            Policy.from_dict(
                {
                    "name": "a",
                    "action_types": ["*"],
                    "condition": "estimated_cost > 0",
                    "verdict": "BLOCK",
                }
            ),
            Policy.from_dict(
                {
                    "name": "b",
                    "action_types": ["*"],
                    "condition": "risk_level == 'HIGH'",
                    "verdict": "BLOCK",
                }
            ),
        ]

        conflicts = pe.detect_conflicts()
        assert len(conflicts) == 0

    def test_conflict_with_wildcard(self):
        """Wildcard (*) overlaps with any specific type."""
        pe = PolicyEngine()
        pe._policies = [
            Policy.from_dict(
                {
                    "name": "a",
                    "action_types": ["*"],
                    "condition": "True",
                    "verdict": "BLOCK",
                }
            ),
            Policy.from_dict(
                {
                    "name": "b",
                    "action_types": ["file.read"],
                    "condition": "True",
                    "verdict": "ALLOW",
                }
            ),
        ]

        conflicts = pe.detect_conflicts()
        assert len(conflicts) == 1

    def test_no_conflict_disjoint_types(self):
        """Different action types = no conflict."""
        pe = PolicyEngine()
        pe._policies = [
            Policy.from_dict(
                {
                    "name": "block_files",
                    "action_types": ["file.*"],
                    "condition": "True",
                    "verdict": "BLOCK",
                }
            ),
            Policy.from_dict(
                {
                    "name": "allow_http",
                    "action_types": ["http.*"],
                    "condition": "True",
                    "verdict": "ALLOW",
                }
            ),
        ]

        conflicts = pe.detect_conflicts()
        assert len(conflicts) == 0

    def test_load_policies_emits_warnings(self):
        """load_policies() warns on conflicts."""
        pe = PolicyEngine()
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pe.load_policies(
                [
                    {
                        "name": "block_it",
                        "action_types": ["file.delete"],
                        "condition": "True",
                        "verdict": "BLOCK",
                    },
                    {
                        "name": "allow_it",
                        "action_types": ["file.delete"],
                        "condition": "True",
                        "verdict": "ALLOW",
                    },
                ]
            )
            assert len(w) >= 1
            assert "Conflict" in str(w[0].message)

    def test_conflict_str_representation(self):
        """PolicyConflict __str__ is human-readable."""
        c = PolicyConflict(
            policy_a="p1",
            policy_b="p2",
            overlapping_types=["file.delete"],
            verdict_a=Verdict.BLOCK,
            verdict_b=Verdict.ALLOW,
        )
        s = str(c)
        assert "p1" in s and "p2" in s
        assert "BLOCK" in s and "ALLOW" in s


# ── 5. Edge Cases ────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases: empty params, None, deep paths, unicode, long strings."""

    def test_empty_parameters(self, engine):
        """Empty parameters dict doesn't crash."""
        intent = _make_intent(action_type="file.read", parameters={})
        result = engine.evaluate(intent)
        assert result.verdict == Verdict.ALLOW

    def test_none_parameter_value(self):
        """None value in parameters handled safely."""
        cc = CompiledCondition(source="parameters.path.startswith('/etc')")
        ctx = {"parameters": {"path": None}}
        # Should not crash — None returns False for startswith
        result = cc.evaluate(ctx)
        assert result is False

    def test_missing_parameter_key(self):
        """Missing key returns empty string, not an error."""
        cc = CompiledCondition(source="parameters.nonexistent.startswith('/etc')")
        ctx = {"parameters": {}}
        result = cc.evaluate(ctx)
        assert result is False

    def test_deeply_nested_dict_access(self):
        """a.b.c.d access chains through nested dicts."""
        cc = CompiledCondition(source="parameters.config.database.host == 'localhost'")
        ctx = {
            "parameters": {
                "config": {"database": {"host": "localhost"}},
            }
        }
        assert cc.evaluate(ctx) is True

    def test_deeply_nested_missing_intermediate(self):
        """Missing intermediate key returns empty string, not crash."""
        cc = CompiledCondition(source="parameters.config.database.host == 'localhost'")
        ctx = {"parameters": {"config": {}}}  # 'database' missing
        assert cc.evaluate(ctx) is False

    def test_unicode_string_in_parameters(self):
        """Unicode strings are handled correctly."""
        cc = CompiledCondition(source="parameters.name == '日本語テスト'")
        ctx = {"parameters": {"name": "日本語テスト"}}
        assert cc.evaluate(ctx) is True

    def test_unicode_startswith(self):
        """startswith works with unicode."""
        cc = CompiledCondition(source="parameters.path.startswith('/données')")
        ctx = {"parameters": {"path": "/données/fichier.txt"}}
        assert cc.evaluate(ctx) is True

    def test_emoji_in_parameter(self):
        """Emoji characters don't break evaluation."""
        cc = CompiledCondition(source="parameters.label == '🔒 Secure'")
        ctx = {"parameters": {"label": "🔒 Secure"}}
        assert cc.evaluate(ctx) is True

    def test_extremely_long_string_value(self):
        """A 100K-character string doesn't crash evaluation."""
        long_str = "A" * 100_000
        cc = CompiledCondition(source="parameters.data.startswith('A')")
        ctx = {"parameters": {"data": long_str}}
        assert cc.evaluate(ctx) is True

    def test_extremely_long_string_comparison(self):
        """Equality on long strings works."""
        long_str = "X" * 10_000
        cc = CompiledCondition(source=f"parameters.data == '{long_str}'")
        ctx = {"parameters": {"data": long_str}}
        assert cc.evaluate(ctx) is True

    def test_in_operator_string(self):
        """'x' in parameters works."""
        cc = CompiledCondition(source="'path' in parameters")
        ctx = {"parameters": {"path": "/tmp/test"}}
        assert cc.evaluate(ctx) is True

    def test_in_operator_string_missing(self):
        """'x' in parameters → False when key missing."""
        cc = CompiledCondition(source="'path' in parameters")
        ctx = {"parameters": {"url": "https://example.com"}}
        assert cc.evaluate(ctx) is False

    def test_not_in_operator(self):
        """'x' not in parameters works."""
        cc = CompiledCondition(source="'secret' not in parameters")
        ctx = {"parameters": {"path": "/tmp"}}
        assert cc.evaluate(ctx) is True

    def test_in_operator_with_list(self):
        """value in [list] works."""
        cc = CompiledCondition(source="action_type in ['file.read', 'file.write']")
        ctx = {"action_type": "file.read", "parameters": {}}
        assert cc.evaluate(ctx) is True

    def test_boolean_literal_true(self):
        """Condition 'True' always triggers."""
        cc = CompiledCondition(source="True")
        assert cc.evaluate({}) is True

    def test_boolean_literal_false(self):
        """Condition 'False' never triggers."""
        cc = CompiledCondition(source="False")
        assert cc.evaluate({}) is False

    def test_ternary_if_expression(self):
        """Ternary if-else in condition."""
        cc = CompiledCondition(
            source="estimated_cost > 1 if risk_level == 'HIGH' else estimated_cost > 5"
        )
        ctx_high = {"estimated_cost": 2.0, "risk_level": "HIGH", "parameters": {}}
        assert cc.evaluate(ctx_high) is True

        ctx_low = {"estimated_cost": 2.0, "risk_level": "LOW", "parameters": {}}
        assert cc.evaluate(ctx_low) is False

    def test_len_function(self):
        """len(parameters) works."""
        cc = CompiledCondition(source="len(parameters) > 2")
        ctx = {"parameters": {"a": 1, "b": 2, "c": 3}}
        assert cc.evaluate(ctx) is True

    def test_parameter_with_special_chars_key(self):
        """Access parameter whose value has special characters."""
        cc = CompiledCondition(source="parameters.cmd.startswith('rm ')")
        ctx = {"parameters": {"cmd": "rm -rf --no-preserve-root /"}}
        assert cc.evaluate(ctx) is True

    def test_invalid_syntax_raises_parse_error(self):
        """Garbage syntax raises PolicyParseError."""
        with pytest.raises(PolicyParseError):
            CompiledCondition(source="if while for +++").evaluate({})

    def test_unsupported_expression_raises_condition_error(self):
        """Unsupported AST nodes raise PolicyConditionError."""
        with pytest.raises(PolicyConditionError):
            CompiledCondition(source="{1, 2, 3}").evaluate({})

    def test_numeric_zero_in_comparison(self):
        """Zero is handled correctly in comparisons."""
        cc = CompiledCondition(source="estimated_cost == 0")
        ctx = {"estimated_cost": 0, "parameters": {}}
        assert cc.evaluate(ctx) is True

    def test_float_precision(self):
        """Floating point comparison works."""
        cc = CompiledCondition(source="estimated_cost > 0.001")
        ctx = {"estimated_cost": 0.002, "parameters": {}}
        assert cc.evaluate(ctx) is True

    def test_negative_numbers(self):
        """Negative numbers in conditions."""
        cc = CompiledCondition(source="estimated_cost < 0")
        ctx = {"estimated_cost": -1.0, "parameters": {}}
        assert cc.evaluate(ctx) is True

    def test_empty_string_startswith(self):
        """Empty string startswith empty string = True."""
        cc = CompiledCondition(source="parameters.path.startswith('')")
        ctx = {"parameters": {"path": ""}}
        assert cc.evaluate(ctx) is True

    def test_dict_get_method(self):
        """parameters.get('key', 'default') works."""
        cc = CompiledCondition(
            source="parameters.get('missing', 'fallback') == 'fallback'"
        )
        ctx = {"parameters": {}}
        assert cc.evaluate(ctx) is True

    def test_subscript_access(self):
        """parameters['key'] subscript access."""
        cc = CompiledCondition(source="parameters['path'] == '/tmp'")
        ctx = {"parameters": {"path": "/tmp"}}
        assert cc.evaluate(ctx) is True
