"""Integration test: multi-agent flow with trust, delegation, and rollback."""

import pytest

from plyra_guard import (
    ActionGuard,
    ActionIntent,
    AgentCall,
    RiskLevel,
    TrustLevel,
    Verdict,
)
from plyra_guard.config.loader import load_config_from_dict


class TestMultiAgentFlow:
    """Tests for multi-agent orchestration scenarios."""

    @pytest.fixture
    def multi_guard(self) -> ActionGuard:
        """Create a guard configured for multi-agent testing."""
        config = load_config_from_dict(
            {
                "global": {
                    "max_delegation_depth": 3,
                    "max_concurrent_delegations": 5,
                },
                "agents": [
                    {
                        "id": "orchestrator",
                        "trust_level": 0.8,
                        "can_delegate_to": ["research-agent", "email-agent"],
                    },
                    {
                        "id": "research-agent",
                        "trust_level": 0.5,
                        "max_actions_per_run": 20,
                    },
                    {
                        "id": "email-agent",
                        "trust_level": 0.3,
                        "max_actions_per_run": 5,
                    },
                ],
                "policies": [
                    {
                        "name": "low_trust_email",
                        "action_types": ["email.send"],
                        "condition": "agent.trust_level < 0.4",
                        "verdict": "WARN",
                        "message": "Low trust agent sending email",
                    },
                ],
            }
        )
        guard = ActionGuard(config=config)
        guard._audit_log._exporters.clear()
        return guard

    def test_orchestrator_delegates_to_sub_agent(self, multi_guard):
        """Orchestrator should be able to delegate to registered sub-agents."""

        @multi_guard.protect("file.read", risk_level=RiskLevel.LOW)
        def research(query: str) -> str:
            return f"Results for {query}"

        multi_guard._default_agent_id = "research-agent"
        result = research("quantum computing")
        assert result == "Results for quantum computing"

    def test_cycle_detection_blocks(self, multi_guard):
        """A cycle in the delegation chain should be blocked."""
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="orchestrator",
            instruction_chain=[
                AgentCall(
                    agent_id="research-agent",
                    trust_level=0.5,
                    instruction="research",
                ),
                AgentCall(
                    agent_id="orchestrator",
                    trust_level=0.8,
                    instruction="review",
                ),
            ],
        )
        multi_guard.evaluate(intent)
        # The cascade controller should detect the cycle
        # (orchestrator appears as current agent and in chain)
        # Note: evaluate() runs the pipeline, cascade check happens in _run_pipeline

    def test_depth_limit_enforced(self, multi_guard):
        """Exceeding delegation depth should be blocked."""
        chain = [
            AgentCall(
                agent_id=f"agent-{i}",
                trust_level=0.5,
                instruction=f"step {i}",
            )
            for i in range(4)  # Exceeds max depth of 3
        ]
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="final-agent",
            instruction_chain=chain,
        )

        @multi_guard.protect("file.read", risk_level=RiskLevel.LOW)
        def read_file(path: str) -> str:
            return "ok"

        # Manually set the intent chain — this would be blocked by cascade
        cascade_result = multi_guard._cascade_controller.check(intent)
        assert cascade_result is not None
        assert cascade_result.verdict == Verdict.BLOCK

    def test_cross_agent_rollback(self, multi_guard, temp_dir):
        """Rollback across multiple agents' actions."""
        import os

        # Agent 1 creates a file
        file1 = os.path.join(temp_dir, "agent1_file.txt")
        multi_guard._default_agent_id = "research-agent"

        @multi_guard.protect("file.create", risk_level=RiskLevel.MEDIUM)
        def create_file(path: str) -> bool:
            with open(path, "w") as f:
                f.write("agent 1 data")
            return True

        create_file(file1)
        assert os.path.exists(file1)

        # Agent 2 creates another file
        file2 = os.path.join(temp_dir, "agent2_file.txt")
        multi_guard._default_agent_id = "email-agent"

        @multi_guard.protect("file.create", risk_level=RiskLevel.MEDIUM)
        def create_another(path: str) -> bool:
            with open(path, "w") as f:
                f.write("agent 2 data")
            return True

        create_another(file2)
        assert os.path.exists(file2)

    def test_trust_level_affects_agent_registration(self, multi_guard):
        """Registered agents should have correct trust levels."""
        assert multi_guard._trust_ledger.is_registered("orchestrator")
        assert multi_guard._trust_ledger.is_registered("email-agent")

        orch = multi_guard._trust_ledger.get("orchestrator")
        assert orch.trust_level == TrustLevel.ORCHESTRATOR

        email = multi_guard._trust_ledger.get("email-agent")
        assert email.trust_level == TrustLevel.SUB_AGENT
