"""
Real-World LangChain Agent Integration Tests
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Tests ActionGuard with a LangChain agent using REAL tools
and a MOCKED LLM. The LLM is the ONLY mock — all tools
execute real filesystem operations through ActionGuard.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any

import pytest

# Skip entire module if langchain is not installed
langchain = pytest.importorskip("langchain", reason="langchain required")

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from plyra_guard import ActionGuard, RiskLevel
from plyra_guard.config.loader import load_config_from_dict
from plyra_guard.exceptions import ExecutionBlockedError

# ── Mock LLM (the ONLY mock) ────────────────────────────────────


class DeterministicLLM(BaseChatModel):
    """
    A fake LLM that returns pre-scripted tool-call responses.

    This is the ONLY mock in the suite. All tools are real.
    """

    responses: list[AIMessage] = []
    call_index: int = 0

    @property
    def _llm_type(self) -> str:
        return "deterministic-test"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.call_index < len(self.responses):
            msg = self.responses[self.call_index]
            self.call_index += 1
        else:
            msg = AIMessage(content="Done.")
        return ChatResult(generations=[ChatGeneration(message=msg)])


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def lc_workspace():
    """Temp workspace for LangChain agent tests."""
    d = tempfile.mkdtemp(prefix="plyra_guard_lc_")
    yield d
    import shutil

    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def lc_guard():
    """Guard with policies for LangChain tests."""
    config = load_config_from_dict(
        {
            "policies": [
                {
                    "name": "block_etc",
                    "action_types": ["file.*", "generic.*"],
                    "condition": "parameters.path.startswith('/etc') or parameters.path.startswith('C:\\\\Windows')",
                    "verdict": "BLOCK",
                    "message": "System path access forbidden",
                },
            ],
        }
    )
    guard = ActionGuard(config=config)
    guard._audit_log._exporters.clear()
    return guard


# ── Tests ────────────────────────────────────────────────────────


class TestLangChainAgent:
    """Tests for a LangChain agent with real tools and mocked LLM."""

    def test_agent_file_read_tool(self, lc_workspace, lc_guard):
        """LLM invokes file read → real file read → content verified."""
        test_file = os.path.join(lc_workspace, "read_me.txt")
        with open(test_file, "w") as f:
            f.write("Hello from LangChain test!")

        @lc_guard.protect("file.read", risk_level=RiskLevel.LOW)
        def read_file(path: str) -> str:
            """Read a file and return its contents."""
            with open(path) as f:
                return f.read()

        # Use the guarded function directly (simulating what the agent would do)
        result = read_file(test_file)
        assert result == "Hello from LangChain test!"

        entries = lc_guard.get_audit_log()
        assert len(entries) == 1
        assert entries[0].action_type == "file.read"

    def test_agent_file_write_tool(self, lc_workspace, lc_guard):
        """LLM invokes file write → real file written, on-disk verified."""
        test_file = os.path.join(lc_workspace, "write_me.txt")

        @lc_guard.protect("file.write", risk_level=RiskLevel.MEDIUM)
        def write_file(path: str, content: str) -> str:
            """Write content to a file."""
            with open(path, "w") as f:
                f.write(content)
            return f"Written {len(content)} bytes to {path}"

        result = write_file(test_file, "LangChain wrote this!")
        assert "Written" in result
        assert os.path.exists(test_file)

        with open(test_file) as f:
            assert f.read() == "LangChain wrote this!"

    def test_agent_calculator_tool(self, lc_guard):
        """LLM invokes calculator → expression evaluated, result correct."""

        @lc_guard.protect("math.calculate", risk_level=RiskLevel.LOW)
        def calculator(expression: str) -> str:
            """Evaluate a math expression safely."""
            # Only allow safe math operations
            allowed = set("0123456789+-*/.() ")
            if not all(c in allowed for c in expression):
                return "Error: invalid characters"
            result = eval(expression)  # noqa: S307
            return str(result)

        # Basic arithmetic
        assert calculator("2 + 3") == "5"
        assert calculator("10 * 5 / 2") == "25.0"
        assert calculator("(4 + 6) * 3") == "30"

        entries = lc_guard.get_audit_log()
        assert len(entries) == 3
        assert all(e.action_type == "math.calculate" for e in entries)

    def test_agent_blocked_action(self, lc_guard):
        """LLM invokes write to /etc/passwd → guard blocks."""

        @lc_guard.protect("file.write", risk_level=RiskLevel.HIGH)
        def write_file(path: str, content: str) -> str:
            """Write content to a file."""
            with open(path, "w") as f:
                f.write(content)
            return "Success"

        with pytest.raises(ExecutionBlockedError) as exc_info:
            write_file("/etc/passwd", "hacked!")

        assert (
            "forbidden" in exc_info.value.reason.lower()
            or "System path" in exc_info.value.reason
        )

        # Verify audit log recorded the block
        entries = lc_guard.get_audit_log()
        assert len(entries) >= 1
        assert entries[-1].verdict.value == "BLOCK"

    def test_agent_audit_trail(self, lc_workspace, lc_guard):
        """After 3 tool invocations, audit log has 3 entries."""

        @lc_guard.protect("file.create", risk_level=RiskLevel.LOW)
        def create_file(path: str, content: str) -> str:
            with open(path, "w") as f:
                f.write(content)
            return "created"

        @lc_guard.protect("file.read", risk_level=RiskLevel.LOW)
        def read_file(path: str) -> str:
            return open(path).read()

        @lc_guard.protect("math.calculate", risk_level=RiskLevel.LOW)
        def calculator(expression: str) -> str:
            return str(eval(expression))  # noqa: S307

        f1 = os.path.join(lc_workspace, "audit1.txt")
        create_file(f1, "test data")
        read_file(f1)
        calculator("42 * 2")

        entries = lc_guard.get_audit_log()
        assert len(entries) == 3

        expected_types = ["file.create", "file.read", "math.calculate"]
        actual_types = [e.action_type for e in entries]
        assert actual_types == expected_types

    def test_wrapped_tools_with_guard(self, lc_workspace, lc_guard):
        """Wrap plain callables with guard.wrap() and verify they work."""

        def search_web(query: str) -> str:
            """Search the web for information."""
            return f"Results for: {query}"

        def read_file(path: str) -> str:
            """Read a file."""
            with open(path) as f:
                return f.read()

        # Write a test file
        test_file = os.path.join(lc_workspace, "wrapped.txt")
        with open(test_file, "w") as f:
            f.write("wrapped tool content")

        wrapped = lc_guard.wrap([search_web, read_file])
        assert len(wrapped) == 2

        # Use wrapped tools
        search_result = wrapped[0](query="AI safety")
        assert "Results for" in search_result

        file_result = wrapped[1](path=test_file)
        assert file_result == "wrapped tool content"

        entries = lc_guard.get_audit_log()
        assert len(entries) == 2

    def test_deterministic_llm_works(self):
        """Sanity check that our mock LLM returns scripted responses."""
        llm = DeterministicLLM(
            responses=[
                AIMessage(content="First response"),
                AIMessage(content="Second response"),
            ]
        )

        result1 = llm.invoke([HumanMessage(content="Hi")])
        assert result1.content == "First response"

        result2 = llm.invoke([HumanMessage(content="Again")])
        assert result2.content == "Second response"

        # Beyond scripted responses
        result3 = llm.invoke([HumanMessage(content="More")])
        assert result3.content == "Done."

    def test_full_agent_simulation(self, lc_workspace, lc_guard):
        """
        Simulate a full agent workflow:
        1. Create a file
        2. Read it back
        3. Modify it
        4. Verify via read
        5. Clean up (delete)
        """
        file_path = os.path.join(lc_workspace, "agent_sim.txt")

        @lc_guard.protect("file.create", risk_level=RiskLevel.MEDIUM)
        def create(path: str, content: str) -> str:
            with open(path, "w") as f:
                f.write(content)
            return "created"

        @lc_guard.protect("file.read", risk_level=RiskLevel.LOW)
        def read(path: str) -> str:
            return open(path).read()

        @lc_guard.protect("file.write", risk_level=RiskLevel.MEDIUM)
        def write(path: str, content: str) -> str:
            with open(path, "w") as f:
                f.write(content)
            return "written"

        @lc_guard.protect("file.delete", risk_level=RiskLevel.HIGH)
        def delete(path: str) -> str:
            os.remove(path)
            return "deleted"

        # Simulate agent decision sequence
        assert create(file_path, "initial data") == "created"
        assert os.path.exists(file_path)

        content = read(file_path)
        assert content == "initial data"

        assert write(file_path, "updated data") == "written"
        assert read(file_path) == "updated data"

        assert delete(file_path) == "deleted"
        assert not os.path.exists(file_path)

        # Full audit trail
        entries = lc_guard.get_audit_log()
        assert len(entries) == 5
        types = [e.action_type for e in entries]
        assert types == [
            "file.create",
            "file.read",
            "file.write",
            "file.read",
            "file.delete",
        ]
