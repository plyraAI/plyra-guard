"""Tests for ActionIntent data model."""

from datetime import datetime

from plyra_guard import ActionIntent, AgentCall, AuditEntry, RiskLevel, Verdict


class TestActionIntent:
    """Tests for the ActionIntent dataclass."""

    def test_auto_generates_action_id(self):
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="agent-1",
        )
        assert intent.action_id
        assert len(intent.action_id) == 36  # UUID format

    def test_default_values(self):
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={"path": "/tmp"},
            agent_id="agent-1",
        )
        assert intent.risk_level == RiskLevel.MEDIUM
        assert intent.estimated_cost == 0.0
        assert intent.task_id is None
        assert intent.instruction_chain == []
        assert intent.metadata == {}

    def test_custom_values(self):
        intent = ActionIntent(
            action_type="shell.exec",
            tool_name="run_command",
            parameters={"cmd": "ls"},
            agent_id="agent-1",
            task_id="task-1",
            estimated_cost=0.5,
            risk_level=RiskLevel.CRITICAL,
        )
        assert intent.action_type == "shell.exec"
        assert intent.risk_level == RiskLevel.CRITICAL
        assert intent.estimated_cost == 0.5
        assert intent.task_id == "task-1"

    def test_timestamp_is_set(self):
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="agent-1",
        )
        assert isinstance(intent.timestamp, datetime)

    def test_instruction_chain(self):
        chain = [
            AgentCall(agent_id="orch", trust_level=0.8, instruction="do X"),
            AgentCall(agent_id="sub", trust_level=0.3, instruction="do Y"),
        ]
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="sub",
            instruction_chain=chain,
        )
        assert len(intent.instruction_chain) == 2
        assert intent.instruction_chain[0].agent_id == "orch"


class TestAuditEntry:
    """Tests for AuditEntry serialization."""

    def test_to_dict(self):
        entry = AuditEntry(
            action_id="test-id",
            agent_id="agent-1",
            action_type="file.read",
            verdict=Verdict.ALLOW,
            risk_score=0.15,
        )
        d = entry.to_dict()
        assert d["action_id"] == "test-id"
        assert d["verdict"] == "ALLOW"
        assert d["risk_score"] == 0.15
        assert "timestamp" in d

    def test_to_dict_with_evaluator_results(self):
        from plyra_guard import EvaluatorResult

        entry = AuditEntry(
            action_id="test-id",
            agent_id="agent-1",
            action_type="file.read",
            verdict=Verdict.ALLOW,
            evaluator_results=[
                EvaluatorResult(
                    verdict=Verdict.ALLOW,
                    reason="OK",
                    evaluator_name="test",
                ),
            ],
        )
        d = entry.to_dict()
        assert len(d["evaluator_results"]) == 1
        assert d["evaluator_results"][0]["verdict"] == "ALLOW"

    def test_to_dict_with_instruction_chain(self):
        entry = AuditEntry(
            action_id="test-id",
            agent_id="agent-1",
            action_type="file.read",
            verdict=Verdict.BLOCK,
            instruction_chain=[
                AgentCall(
                    agent_id="orch",
                    trust_level=0.8,
                    instruction="test",
                ),
            ],
        )
        d = entry.to_dict()
        assert len(d["instruction_chain"]) == 1
        assert d["instruction_chain"][0]["agent_id"] == "orch"
