"""Tests for the Trust Ledger."""

import pytest

from plyra_guard.core.verdict import TrustLevel
from plyra_guard.exceptions import AgentNotRegisteredError
from plyra_guard.multiagent.trust_ledger import TrustLedger


class TestTrustLedger:
    """Tests for the trust ledger."""

    def test_register_agent(self):
        ledger = TrustLedger()
        profile = ledger.register("agent-1", TrustLevel.ORCHESTRATOR)
        assert profile.agent_id == "agent-1"
        assert profile.trust_score == 0.8

    def test_get_registered_agent(self):
        ledger = TrustLedger()
        ledger.register("agent-1", TrustLevel.PEER)
        profile = ledger.get("agent-1")
        assert profile.trust_level == TrustLevel.PEER

    def test_unknown_agent_raises_when_blocking(self):
        ledger = TrustLedger(block_unknown=True)
        with pytest.raises(AgentNotRegisteredError):
            ledger.get("unknown-agent")

    def test_unknown_agent_returns_default_when_not_blocking(self):
        ledger = TrustLedger(block_unknown=False)
        profile = ledger.get("unknown-agent")
        assert profile.trust_level == TrustLevel.UNKNOWN
        assert profile.trust_score == 0.0

    def test_record_action_updates_count(self):
        ledger = TrustLedger()
        ledger.register("agent-1", TrustLevel.PEER)
        ledger.record_action("agent-1", success=True)
        ledger.record_action("agent-1", success=False)
        profile = ledger.get("agent-1")
        assert profile.action_count == 2
        assert profile.error_count == 1

    def test_record_violation_reduces_trust(self):
        ledger = TrustLedger()
        ledger.register("agent-1", TrustLevel.PEER)
        initial_trust = ledger.get("agent-1").trust_score
        ledger.record_violation("agent-1")
        assert ledger.get("agent-1").trust_score < initial_trust

    def test_delegation_check(self):
        ledger = TrustLedger()
        ledger.register(
            "orchestrator",
            TrustLevel.ORCHESTRATOR,
            can_delegate_to=["worker-1"],
        )
        assert ledger.can_delegate("orchestrator", "worker-1") is True
        assert ledger.can_delegate("orchestrator", "worker-2") is False

    def test_error_rate_calculation(self):
        ledger = TrustLedger()
        ledger.register("agent-1", TrustLevel.PEER)
        for _ in range(8):
            ledger.record_action("agent-1", success=True)
        for _ in range(2):
            ledger.record_action("agent-1", success=False)

        profile = ledger.get("agent-1")
        assert abs(profile.error_rate - 0.2) < 0.01
