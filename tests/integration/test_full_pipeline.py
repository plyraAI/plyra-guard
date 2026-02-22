"""Integration test: full single-agent pipeline end-to-end."""

import os

import pytest

from plyra_guard import ActionGuard, ActionIntent, RiskLevel, Verdict
from plyra_guard.exceptions import ExecutionBlockedError


class TestFullPipeline:
    """End-to-end tests for the single-agent pipeline."""

    def test_protect_decorator_allows_safe_action(self, guard):
        """A low-risk action should be allowed and return normally."""

        @guard.protect("file.read", risk_level=RiskLevel.LOW)
        def read_file(path: str) -> str:
            return f"contents of {path}"

        result = read_file("/tmp/test.txt")
        assert result == "contents of /tmp/test.txt"

    def test_protect_decorator_blocks_policy_violation(self):
        """An action violating a policy should be blocked."""
        from plyra_guard.config.loader import load_config_from_dict

        config = load_config_from_dict(
            {
                "policies": [
                    {
                        "name": "block_etc",
                        "action_types": ["file.delete"],
                        "condition": "parameters.path.startswith('/etc')",
                        "verdict": "BLOCK",
                        "message": "Cannot delete system files",
                    },
                ],
            }
        )
        guard = ActionGuard(config=config)
        guard._audit_log._exporters.clear()

        @guard.protect("file.delete", risk_level=RiskLevel.HIGH)
        def delete_file(path: str) -> bool:
            os.remove(path)
            return True

        with pytest.raises(ExecutionBlockedError):
            delete_file("/etc/important.conf")

    def test_evaluate_dry_run(self, guard):
        """Evaluate without executing."""
        intent = ActionIntent(
            action_type="file.read",
            tool_name="read_file",
            parameters={"path": "/tmp/test.txt"},
            agent_id="test-agent",
        )
        result = guard.evaluate(intent)
        assert result.verdict in (Verdict.ALLOW, Verdict.WARN)

    def test_audit_log_records_actions(self, guard):
        """Every action should be recorded in the audit log."""

        @guard.protect("file.read", risk_level=RiskLevel.LOW)
        def read_file(path: str) -> str:
            return "ok"

        read_file("/tmp/test.txt")

        entries = guard.get_audit_log()
        assert len(entries) >= 1
        assert entries[-1].action_type == "file.read"

    def test_metrics_updated(self, guard):
        """Metrics should reflect actions."""

        @guard.protect("file.read", risk_level=RiskLevel.LOW)
        def read_file(path: str) -> str:
            return "ok"

        read_file("/tmp/test.txt")

        metrics = guard.get_metrics()
        assert metrics.total_actions > 0

    def test_rollback_file_operation(self, guard, temp_file):
        """Rollback should restore a deleted file."""
        action_id = None

        @guard.protect("file.delete", risk_level=RiskLevel.HIGH)
        def delete_file(path: str) -> bool:
            os.remove(path)
            return True

        # We need to capture the action_id from the audit log
        delete_file(temp_file)
        assert not os.path.exists(temp_file)

        # Get the action_id from the audit log
        entries = guard.get_audit_log()
        action_id = entries[-1].action_id

        # Rollback
        success = guard.rollback(action_id)
        assert success is True
        assert os.path.exists(temp_file)

    def test_wrap_openai_tools(self, guard):
        """Wrapping OpenAI tools should return the same format."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {},
                },
            },
        ]
        wrapped = guard.wrap(tools)
        assert len(wrapped) == 1
        assert wrapped[0]["function"]["name"] == "get_weather"
        assert "_plyra_guard" in wrapped[0]
