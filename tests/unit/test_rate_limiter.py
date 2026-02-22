"""Tests for the Rate Limiter evaluator."""

import pytest

from plyra_guard import ActionIntent, Verdict
from plyra_guard.evaluators.rate_limiter import RateLimit, RateLimiter


class TestRateLimit:
    """Tests for RateLimit parsing."""

    def test_parse_per_minute(self):
        rl = RateLimit.from_string("60/min")
        assert rl.max_calls == 60
        assert rl.period_seconds == 60

    def test_parse_per_second(self):
        rl = RateLimit.from_string("10/sec")
        assert rl.max_calls == 10
        assert rl.period_seconds == 1

    def test_parse_per_hour(self):
        rl = RateLimit.from_string("100/hour")
        assert rl.max_calls == 100
        assert rl.period_seconds == 3600

    def test_invalid_format_raises(self):
        with pytest.raises(ValueError):
            RateLimit.from_string("invalid")

    def test_invalid_period_raises(self):
        with pytest.raises(ValueError):
            RateLimit.from_string("10/fortnight")


class TestRateLimiter:
    """Tests for the rate limiter evaluator."""

    def test_allows_within_limit(self):
        limiter = RateLimiter(default_limit="10/min")
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="agent-1",
        )
        result = limiter.evaluate(intent)
        assert result.verdict == Verdict.ALLOW

    def test_blocks_when_exceeded(self):
        limiter = RateLimiter(default_limit="3/min")
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="agent-1",
        )
        # Use up the limit
        for _ in range(3):
            limiter.evaluate(intent)

        # Should be blocked now
        result = limiter.evaluate(intent)
        assert result.verdict == Verdict.BLOCK
        assert "Rate limit exceeded" in result.reason

    def test_per_tool_limits(self):
        limiter = RateLimiter(
            default_limit="100/min",
            per_tool_limits={"email.send": "2/min"},
        )
        intent = ActionIntent(
            action_type="email.send",
            tool_name="send_email",
            parameters={},
            agent_id="agent-1",
        )
        limiter.evaluate(intent)
        limiter.evaluate(intent)

        result = limiter.evaluate(intent)
        assert result.verdict == Verdict.BLOCK

    def test_different_agents_separate_counters(self):
        limiter = RateLimiter(default_limit="2/min")
        intent1 = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="agent-1",
        )
        intent2 = ActionIntent(
            action_type="file.read",
            tool_name="read",
            parameters={},
            agent_id="agent-2",
        )

        limiter.evaluate(intent1)
        limiter.evaluate(intent1)

        # Agent 2 should still be allowed
        result = limiter.evaluate(intent2)
        assert result.verdict == Verdict.ALLOW

    def test_evaluator_name(self):
        limiter = RateLimiter()
        assert limiter.name == "rate_limiter"
