"""Shared fixtures for ActionGuard tests."""

from __future__ import annotations

import os
import tempfile

import pytest

from plyra_guard import ActionGuard, ActionIntent, AgentCall, RiskLevel


@pytest.fixture
def guard() -> ActionGuard:
    """Create a default ActionGuard instance for testing."""
    g = ActionGuard.default()
    # Disable stdout exporter for cleaner test output
    g._audit_log._exporters.clear()
    return g


@pytest.fixture
def sample_intent() -> ActionIntent:
    """Create a sample ActionIntent for testing."""
    return ActionIntent(
        action_type="file.read",
        tool_name="read_file",
        parameters={"path": "/tmp/test.txt"},
        agent_id="test-agent",
        task_id="task-001",
        task_context="Reading a test file for unit testing",
        estimated_cost=0.01,
        risk_level=RiskLevel.LOW,
    )


@pytest.fixture
def high_risk_intent() -> ActionIntent:
    """Create a high-risk ActionIntent for testing."""
    return ActionIntent(
        action_type="file.delete",
        tool_name="delete_file",
        parameters={"path": "/etc/passwd"},
        agent_id="test-agent",
        task_id="task-001",
        task_context="Deleting a system file",
        estimated_cost=0.0,
        risk_level=RiskLevel.CRITICAL,
    )


@pytest.fixture
def delegation_intent() -> ActionIntent:
    """Create an ActionIntent with delegation chain."""
    return ActionIntent(
        action_type="email.send",
        tool_name="send_email",
        parameters={
            "to": "user@example.com",
            "subject": "Test",
            "body": "Hello",
        },
        agent_id="email-agent",
        task_id="task-002",
        task_context="Sending an email",
        risk_level=RiskLevel.MEDIUM,
        instruction_chain=[
            AgentCall(
                agent_id="orchestrator",
                trust_level=0.8,
                instruction="Send a confirmation email",
            ),
            AgentCall(
                agent_id="email-agent",
                trust_level=0.3,
                instruction="Compose and send the email",
            ),
        ],
    )


@pytest.fixture
def temp_dir():
    """Create a temporary directory for file tests."""
    d = tempfile.mkdtemp(prefix="plyra_guard_test_")
    yield d
    # Cleanup
    import shutil

    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def temp_file(temp_dir):
    """Create a temporary file for testing."""
    path = os.path.join(temp_dir, "test_file.txt")
    with open(path, "w") as f:
        f.write("original content")
    return path
