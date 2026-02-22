"""Tests for the Policy Engine evaluator."""

import pytest

from plyra_guard import ActionIntent, Verdict
from plyra_guard.evaluators.policy_engine import Policy, PolicyEngine


@pytest.fixture
def engine() -> PolicyEngine:
    """Create a policy engine with test policies."""
    pe = PolicyEngine()
    pe.load_policies(
        [
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
                "name": "block_wildcard_delete",
                "action_types": ["file.delete"],
                "condition": "parameters.path == '*'",
                "verdict": "BLOCK",
                "message": "Wildcard deletes are forbidden",
            },
            {
                "name": "warn_low_trust",
                "action_types": ["email.send"],
                "condition": "agent.trust_level < 0.5",
                "verdict": "WARN",
                "message": "Low trust agent sending email",
            },
            {
                "name": "pii_guard",
                "action_types": ["http.post"],
                "condition": "contains_pii(parameters)",
                "verdict": "BLOCK",
                "message": "PII detected in outbound request",
            },
        ]
    )
    return pe


class TestPolicyEngine:
    """Tests for the policy engine evaluator."""

    def test_blocks_system_path(self, engine):
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read_file",
            parameters={"path": "/etc/passwd"},
            agent_id="agent-1",
        )
        result = engine.evaluate(intent)
        assert result.verdict == Verdict.BLOCK
        assert "System path" in result.reason

    def test_allows_normal_path(self, engine):
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read_file",
            parameters={"path": "/home/user/data.txt"},
            agent_id="agent-1",
        )
        result = engine.evaluate(intent)
        assert result.verdict == Verdict.ALLOW

    def test_escalates_high_cost(self, engine):
        intent = ActionIntent(
            action_type="http.get",
            tool_name="fetch",
            parameters={},
            agent_id="agent-1",
            estimated_cost=1.50,
        )
        result = engine.evaluate(intent)
        assert result.verdict == Verdict.ESCALATE

    def test_allows_low_cost(self, engine):
        intent = ActionIntent(
            action_type="http.get",
            tool_name="fetch",
            parameters={},
            agent_id="agent-1",
            estimated_cost=0.10,
        )
        result = engine.evaluate(intent)
        assert result.verdict == Verdict.ALLOW

    def test_blocks_pii_in_post(self, engine):
        intent = ActionIntent(
            action_type="http.post",
            tool_name="send_data",
            parameters={"email": "user@example.com", "ssn": "123-45-6789"},
            agent_id="agent-1",
        )
        result = engine.evaluate(intent)
        assert result.verdict == Verdict.BLOCK
        assert "PII" in result.reason

    def test_action_type_glob_matching(self, engine):
        intent = ActionIntent(
            action_type="db.select",
            tool_name="query",
            parameters={},
            agent_id="agent-1",
            estimated_cost=0.01,
        )
        result = engine.evaluate(intent)
        assert result.verdict == Verdict.ALLOW

    def test_policy_from_dict(self):
        p = Policy.from_dict(
            {
                "name": "test_policy",
                "action_types": ["*"],
                "condition": "estimated_cost > 10",
                "verdict": "BLOCK",
            }
        )
        assert p.name == "test_policy"
        assert p.verdict == Verdict.BLOCK

    def test_empty_policies_allow(self):
        engine = PolicyEngine()
        intent = ActionIntent(
            action_type="file.delete",
            tool_name="delete",
            parameters={},
            agent_id="agent-1",
        )
        result = engine.evaluate(intent)
        assert result.verdict == Verdict.ALLOW

    def test_sys_path_blocked(self, engine):
        intent = ActionIntent(
            action_type="file.write",
            tool_name="write_file",
            parameters={"path": "/sys/firmware/config"},
            agent_id="agent-1",
        )
        result = engine.evaluate(intent)
        assert result.verdict == Verdict.BLOCK
