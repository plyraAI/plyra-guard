"""Tests for the Cascade Controller."""

from plyra_guard import ActionIntent, AgentCall, Verdict
from plyra_guard.multiagent.cascade_controller import CascadeController


class TestCascadeController:
    """Tests for cascade controller limits."""

    def test_allows_within_depth_limit(self):
        cc = CascadeController(max_delegation_depth=4)
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="agent-3",
            instruction_chain=[
                AgentCall(agent_id="orch", trust_level=0.8, instruction="a"),
                AgentCall(agent_id="sub1", trust_level=0.5, instruction="b"),
            ],
        )
        result = cc.check(intent)
        assert result is None  # No issues

    def test_blocks_excessive_depth(self):
        cc = CascadeController(max_delegation_depth=2)
        chain = [
            AgentCall(agent_id=f"agent-{i}", trust_level=0.5, instruction="x")
            for i in range(3)
        ]
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="agent-99",
            instruction_chain=chain,
        )
        result = cc.check(intent)
        assert result is not None
        assert result.verdict == Verdict.BLOCK
        assert "depth" in result.reason.lower()

    def test_detects_cycle(self):
        cc = CascadeController()
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="agent-1",  # Same as in chain
            instruction_chain=[
                AgentCall(agent_id="orch", trust_level=0.8, instruction="a"),
                AgentCall(agent_id="agent-1", trust_level=0.5, instruction="b"),
            ],
        )
        result = cc.check(intent)
        assert result is not None
        assert result.verdict == Verdict.BLOCK
        assert "cycle" in result.reason.lower()

    def test_detects_duplicate_in_chain(self):
        cc = CascadeController()
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="agent-99",
            instruction_chain=[
                AgentCall(agent_id="agent-1", trust_level=0.8, instruction="a"),
                AgentCall(agent_id="agent-2", trust_level=0.5, instruction="b"),
                AgentCall(agent_id="agent-1", trust_level=0.8, instruction="c"),
            ],
        )
        result = cc.check(intent)
        assert result is not None
        assert result.verdict == Verdict.BLOCK

    def test_concurrent_delegation_limit(self):
        cc = CascadeController(max_concurrent_delegations=2)

        # Simulate 2 active delegations
        cc.record_delegation_start("orch")
        cc.record_delegation_start("orch")

        intent = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="sub-3",
            instruction_chain=[
                AgentCall(agent_id="orch", trust_level=0.8, instruction="a"),
            ],
        )
        result = cc.check(intent)
        assert result is not None
        assert result.verdict == Verdict.BLOCK
        assert "concurrent" in result.reason.lower()

    def test_no_chain_passes(self):
        cc = CascadeController()
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="agent-1",
        )
        result = cc.check(intent)
        assert result is None

    def test_reset_clears_counters(self):
        cc = CascadeController()
        cc.record_delegation_start("orch")
        cc.reset()
        assert cc.get_active_count("orch") == 0
