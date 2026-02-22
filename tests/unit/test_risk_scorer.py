"""Tests for the Risk Scorer evaluator."""

import pytest

from plyra_guard import ActionIntent, Verdict
from plyra_guard.evaluators.risk_scorer import RiskScorer


@pytest.fixture
def scorer() -> RiskScorer:
    return RiskScorer()


class TestRiskScorer:
    """Tests for the risk scoring engine."""

    def test_low_risk_read_action(self, scorer):
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read_file",
            parameters={"path": "/tmp/test.txt"},
            agent_id="agent-1",
            task_context="Reading file for testing",
        )
        result = scorer.evaluate(intent)
        assert result.verdict in (Verdict.ALLOW, Verdict.WARN)
        score = result.metadata["risk_score"]
        assert score < 0.5

    def test_high_risk_delete_action(self, scorer):
        intent = ActionIntent(
            action_type="file.delete",
            tool_name="delete_file",
            parameters={"path": "/etc/important.conf"},
            agent_id="agent-1",
        )
        result = scorer.evaluate(intent)
        score = result.metadata["risk_score"]
        assert score > 0.3

    def test_shell_exec_highest_risk(self, scorer):
        intent = ActionIntent(
            action_type="shell.exec",
            tool_name="run_shell",
            parameters={"cmd": "rm -rf /"},
            agent_id="agent-1",
        )
        result = scorer.evaluate(intent)
        score = result.metadata["risk_score"]
        assert score > 0.25  # shell.exec base risk 0.9 × 0.30 weight = 0.27+

    def test_sensitive_parameters_increase_risk(self, scorer):
        intent = ActionIntent(
            action_type="http.post",
            tool_name="send_data",
            parameters={
                "api_key": "sk-12345",
                "password": "secret123",
            },
            agent_id="agent-1",
        )
        result = scorer.evaluate(intent)
        score = result.metadata["risk_score"]
        # Should be higher than a clean POST
        clean_intent = ActionIntent(
            action_type="http.post",
            tool_name="send_data",
            parameters={"message": "hello"},
            agent_id="agent-1",
        )
        clean_result = scorer.evaluate(clean_intent)
        clean_score = clean_result.metadata["risk_score"]
        assert score > clean_score

    def test_agent_violations_increase_risk(self, scorer):
        intent = ActionIntent(
            action_type="http.get",
            tool_name="fetch",
            parameters={},
            agent_id="agent-1",
            metadata={
                "agent_error_rate": 0.5,
                "agent_violations": 3,
            },
        )
        result = scorer.evaluate(intent)
        score = result.metadata["risk_score"]
        # Clean agent
        clean = ActionIntent(
            action_type="http.get",
            tool_name="fetch",
            parameters={},
            agent_id="agent-1",
            metadata={"agent_error_rate": 0.0, "agent_violations": 0},
        )
        clean_result = scorer.evaluate(clean)
        assert score > clean_result.metadata["risk_score"]

    def test_compute_score_is_bounded(self, scorer):
        intent = ActionIntent(
            action_type="shell.exec",
            tool_name="exec",
            parameters={
                "cmd": "rm -rf /etc/",
                "password": "secret",
                "token": "abc",
                "targets": ["all"],
            },
            agent_id="agent-1",
            metadata={"agent_error_rate": 1.0, "agent_violations": 10},
        )
        score = scorer.compute_score(intent)
        assert 0.0 <= score <= 1.0

    def test_unknown_action_type_gets_medium_risk(self, scorer):
        intent = ActionIntent(
            action_type="custom.unknown",
            tool_name="mystery",
            parameters={},
            agent_id="agent-1",
        )
        score = scorer.compute_score(intent)
        assert 0.0 <= score <= 1.0
