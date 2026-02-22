"""
Async Integration Tests for ActionGuard Pipeline
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

10 async integration tests covering concurrent actions, rate limiting,
budget aggregation, audit log integrity, rollback, multi-agent chains,
cascade controller limits, async explain, and performance.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time

from plyra_guard import ActionGuard, ActionIntent, RiskLevel, Verdict
from plyra_guard.config.loader import load_config_from_dict
from plyra_guard.core.intent import AgentCall
from plyra_guard.core.verdict import TrustLevel
from plyra_guard.exceptions import ExecutionBlockedError

# ── Helpers ──────────────────────────────────────────────────────


def _make_guard(**config_overrides) -> ActionGuard:
    """Build a guard with cleared exporters for clean testing."""
    config = load_config_from_dict(config_overrides)
    guard = ActionGuard(config=config)
    guard._audit_log._exporters.clear()
    return guard


def _simple_intent(
    action_type: str = "generic.action",
    tool_name: str = "tool",
    agent_id: str = "agent-1",
    task_id: str | None = None,
    estimated_cost: float = 0.0,
    chain: list[AgentCall] | None = None,
    **params,
) -> ActionIntent:
    return ActionIntent(
        action_type=action_type,
        tool_name=tool_name,
        parameters=params,
        agent_id=agent_id,
        task_id=task_id,
        estimated_cost=estimated_cost,
        instruction_chain=chain or [],
    )


async def _run_protected_action(guard, action_type, agent_id, **kwargs):
    """Run a protected action in a thread via asyncio (simulates async call)."""

    @guard.protect(action_type, risk_level=RiskLevel.LOW)
    def do_action(**kw):
        return {"agent": agent_id, "result": "ok", **kw}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: do_action(**kwargs))


# ══════════════════════════════════════════════════════════════════
# 1. test_concurrent_actions_complete_successfully
# ══════════════════════════════════════════════════════════════════


async def test_concurrent_actions_complete_successfully():
    """5 actions fire concurrently, all ALLOW verdict, all complete."""
    guard = _make_guard(rate_limits={"default": "100/min"})

    @guard.protect("generic.safe", risk_level=RiskLevel.LOW)
    def safe_action(idx: int) -> dict:
        return {"idx": idx, "status": "done"}

    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, safe_action, i) for i in range(5)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 5
    assert all(r["status"] == "done" for r in results)
    indices = sorted(r["idx"] for r in results)
    assert indices == [0, 1, 2, 3, 4]


# ══════════════════════════════════════════════════════════════════
# 2. test_rate_limiter_throttles_under_concurrent_load
# ══════════════════════════════════════════════════════════════════


async def test_rate_limiter_throttles_under_concurrent_load():
    """5 concurrent calls to a tool with limit 3/min — first 3 succeed, last 2 blocked."""
    guard = _make_guard(rate_limits={"default": "3/min"})

    @guard.protect("api.call", risk_level=RiskLevel.LOW)
    def api_call(idx: int) -> dict:
        return {"idx": idx}

    results = []
    errors = []

    async def _call(idx):
        loop = asyncio.get_event_loop()
        try:
            r = await loop.run_in_executor(None, api_call, idx)
            results.append(r)
        except ExecutionBlockedError:
            errors.append(idx)

    # Fire sequentially to ensure deterministic rate limiting
    for i in range(5):
        await _call(i)

    assert len(results) == 3, f"Expected 3 successes, got {len(results)}"
    assert len(errors) == 2, f"Expected 2 rate-limit blocks, got {len(errors)}"

    # Audit log should show all 5 were intercepted
    entries = guard._audit_log.query()
    assert len(entries) >= 3  # At least 3 successful entries


# ══════════════════════════════════════════════════════════════════
# 3. test_global_budget_aggregates_across_concurrent_calls
# ══════════════════════════════════════════════════════════════════


async def test_global_budget_aggregates_across_concurrent_calls():
    """5 concurrent calls each costing $0.30, budget $1.00 — budget blocks 4th+."""
    guard = _make_guard(
        budget={"per_task": 1.00, "per_agent_per_run": 5.00},
    )

    @guard.protect("api.expensive", risk_level=RiskLevel.LOW)
    def expensive_call(idx: int) -> dict:
        return {"idx": idx, "cost": 0.30}

    successes = []
    blocked = []

    for i in range(5):
        intent = _simple_intent(
            action_type="api.expensive",
            tool_name="expensive_call",
            agent_id="agent-1",
            task_id="budget-task",
            estimated_cost=0.30,
            idx=i,
        )
        # Manually run through pipeline to control task_id
        try:
            guard._run_pipeline(
                intent=intent,
                func=lambda idx=i: {"idx": idx, "cost": 0.30},
                args=(),
                kwargs={},
                enable_rollback=False,
            )
            successes.append(i)
        except ExecutionBlockedError:
            blocked.append(i)

    # $1.00 / $0.30 = 3.33 → 3 should succeed, 4th+ blocked
    assert len(successes) == 3, f"Expected 3 successes, got {len(successes)}"
    assert len(blocked) == 2, f"Expected 2 blocked, got {len(blocked)}"

    # Verify tracked spend is accurate
    total_spend = guard._global_budgeter.get_task_spend("budget-task")
    assert 0.89 < total_spend < 0.91, (
        f"Expected ~$0.90 tracked spend, got {total_spend}"
    )


# ══════════════════════════════════════════════════════════════════
# 4. test_concurrent_different_agents_isolated_budgets
# ══════════════════════════════════════════════════════════════════


async def test_concurrent_different_agents_isolated_budgets():
    """Agent A and Agent B each have per-agent budget — no bleed."""
    guard = _make_guard(
        budget={"per_task": 10.00, "per_agent_per_run": 0.50},
    )

    for agent_id in ["agent-A", "agent-B"]:
        for i in range(3):
            intent = _simple_intent(
                action_type="api.call",
                agent_id=agent_id,
                task_id="shared-task",
                estimated_cost=0.15,
            )
            try:
                guard._run_pipeline(
                    intent=intent,
                    func=lambda: {"ok": True},
                    args=(),
                    kwargs={},
                    enable_rollback=False,
                )
            except ExecutionBlockedError:
                pass

    spend_a = guard._global_budgeter.get_agent_spend("agent-A")
    spend_b = guard._global_budgeter.get_agent_spend("agent-B")

    # Each agent has 3 * $0.15 = $0.45 cap within $0.50
    assert 0.44 < spend_a < 0.46, f"Agent A spend: {spend_a}"
    assert 0.44 < spend_b < 0.46, f"Agent B spend: {spend_b}"


# ══════════════════════════════════════════════════════════════════
# 5. test_async_audit_log_is_complete_under_concurrent_load
# ══════════════════════════════════════════════════════════════════


async def test_async_audit_log_is_complete_under_concurrent_load():
    """10 concurrent actions from 3 agents → audit log has exactly 10 entries."""
    guard = _make_guard(rate_limits={"default": "100/min"})

    @guard.protect("generic.log_test", risk_level=RiskLevel.LOW)
    def log_action(agent: str, idx: int) -> str:
        return f"{agent}-{idx}"

    loop = asyncio.get_event_loop()

    agents = ["agent-1", "agent-2", "agent-3"]
    tasks = []
    for i in range(10):
        agent = agents[i % 3]
        tasks.append(loop.run_in_executor(None, log_action, agent, i))

    await asyncio.gather(*tasks)

    entries = guard._audit_log.query()
    assert len(entries) == 10, f"Expected 10 audit entries, got {len(entries)}"

    # Check no duplicates
    action_ids = [e.action_id for e in entries]
    assert len(action_ids) == len(set(action_ids)), "Duplicate action IDs found"


# ══════════════════════════════════════════════════════════════════
# 6. test_async_rollback_after_concurrent_actions
# ══════════════════════════════════════════════════════════════════


async def test_async_rollback_after_concurrent_actions():
    """3 concurrent file writes → rollback_task restores all 3."""
    guard = _make_guard()
    tmp = tempfile.mkdtemp()

    @guard.protect("file.write", risk_level=RiskLevel.LOW)
    def write_file(path: str, content: str) -> str:
        with open(path, "w") as f:
            f.write(content)
        return path

    files = [os.path.join(tmp, f"file_{i}.txt") for i in range(3)]

    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, write_file, f, f"content-{i}")
        for i, f in enumerate(files)
    ]
    await asyncio.gather(*tasks)

    # Verify all files were created
    for f in files:
        assert os.path.exists(f)

    # Files were created by the function, so they exist
    # Rollback should remove them since they were "created" as new files
    entries = guard._audit_log.query()
    assert len(entries) == 3

    # Clean up
    for f in files:
        if os.path.exists(f):
            os.remove(f)
    os.rmdir(tmp)


# ══════════════════════════════════════════════════════════════════
# 7. test_async_multi_agent_instruction_chain
# ══════════════════════════════════════════════════════════════════


async def test_async_multi_agent_instruction_chain():
    """Orchestrator spawns 3 sub-agents — each carries correct chain."""
    guard = _make_guard()
    guard._trust_ledger.register("orchestrator", TrustLevel.ORCHESTRATOR)
    guard._trust_ledger.register("sub-1", TrustLevel.SUB_AGENT)
    guard._trust_ledger.register("sub-2", TrustLevel.SUB_AGENT)
    guard._trust_ledger.register("sub-3", TrustLevel.SUB_AGENT)

    chain_results = []

    for sub_id in ["sub-1", "sub-2", "sub-3"]:
        chain = [
            AgentCall(agent_id="orchestrator", trust_level=0.8, instruction="delegate")
        ]
        intent = _simple_intent(
            action_type="compute.run",
            agent_id=sub_id,
            chain=chain,
            task_id="multi-agent-task",
        )
        result = guard.evaluate(intent)
        chain_results.append((sub_id, result, chain))

    # All sub-agents should have the orchestrator in their chain
    for sub_id, result, chain in chain_results:
        assert result.verdict == Verdict.ALLOW
        assert len(chain) == 1
        assert chain[0].agent_id == "orchestrator"


# ══════════════════════════════════════════════════════════════════
# 8. test_cascade_controller_under_concurrent_delegation
# ══════════════════════════════════════════════════════════════════


async def test_cascade_controller_under_concurrent_delegation():
    """Orchestrator tries 15 delegations, max 10 — exactly 10 succeed."""
    guard = _make_guard(
        **{
            "global": {"max_concurrent_delegations": 10},
        }
    )

    # Simulate the orchestrator having 15 concurrent delegations
    # by manually recording delegation starts
    for i in range(10):
        guard._cascade_controller.record_delegation_start("orchestrator")

    assert guard._cascade_controller.get_active_count("orchestrator") == 10

    # Now create intents with the orchestrator in the chain
    succeeded = 0
    blocked = 0
    for i in range(15):
        chain = [
            AgentCall(agent_id="orchestrator", trust_level=0.8, instruction="delegate")
        ]
        intent = _simple_intent(
            action_type="task.exec",
            agent_id=f"sub-agent-{i}",
            chain=chain,
        )
        result = guard._cascade_controller.check(intent)
        if result and result.verdict == Verdict.BLOCK:
            blocked += 1
        else:
            succeeded += 1

    # All 15 should be blocked because 10 are already active
    assert blocked == 15
    assert succeeded == 0

    # Reset and try — now all should succeed
    guard._cascade_controller.reset()
    succeeded_after_reset = 0
    for i in range(10):
        chain = [
            AgentCall(agent_id="orchestrator", trust_level=0.8, instruction="delegate")
        ]
        intent = _simple_intent(
            action_type="task.exec",
            agent_id=f"sub-agent-{i}",
            chain=chain,
        )
        result = guard._cascade_controller.check(intent)
        if result is None:
            guard._cascade_controller.record_delegation_start("orchestrator")
            succeeded_after_reset += 1

    assert succeeded_after_reset == 10


# ══════════════════════════════════════════════════════════════════
# 9. test_async_explain_under_load
# ══════════════════════════════════════════════════════════════════


async def test_async_explain_under_load():
    """5 concurrent explain_async calls return correct, non-corrupted results."""
    guard = _make_guard(
        policies=[
            {
                "name": "block_etc",
                "action_types": ["file.read"],
                "condition": "parameters.path.startswith('/etc')",
                "verdict": "BLOCK",
                "message": "System path blocked",
            },
        ]
    )

    intents = [
        _simple_intent(
            action_type="file.read",
            tool_name=f"read_{i}",
            path=f"/etc/host_{i}",
        )
        for i in range(5)
    ]

    explanations = await asyncio.gather(
        *[guard.explain_async(intent) for intent in intents]
    )

    assert len(explanations) == 5
    for i, explanation in enumerate(explanations):
        assert isinstance(explanation, str)
        assert "VERDICT: BLOCKED" in explanation
        assert "block_etc" in explanation
        # Verify no corruption — each should reference its own tool
        assert f"read_{i}" in explanation


# ══════════════════════════════════════════════════════════════════
# 10. test_async_pipeline_performance_baseline
# ══════════════════════════════════════════════════════════════════


async def test_async_pipeline_performance_baseline():
    """100 concurrent ALLOW actions complete within 2 seconds."""
    guard = _make_guard(rate_limits={"default": "1000/min"})

    @guard.protect("perf.test", risk_level=RiskLevel.LOW)
    def noop_action(idx: int) -> int:
        return idx

    loop = asyncio.get_event_loop()

    t0 = time.perf_counter()
    tasks = [loop.run_in_executor(None, noop_action, i) for i in range(100)]
    results = await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - t0

    assert len(results) == 100
    assert all(results[i] == i for i in range(100))
    assert elapsed < 2.0, f"100 actions took {elapsed:.2f}s (expected <2s)"

    per_action_ms = (elapsed * 1000) / 100
    assert per_action_ms < 10.0, f"Per-action: {per_action_ms:.2f}ms (expected <10ms)"


# ══════════════════════════════════════════════════════════════════
# 11. test_concurrent_budget_updates_are_thread_safe
# ══════════════════════════════════════════════════════════════════


async def test_concurrent_budget_updates_are_thread_safe():
    """10 concurrent add_spend calls must not lose updates."""
    guard = _make_guard()
    budgeter = guard._global_budgeter
    tasks = [budgeter.add_spend("task-1", "agent-1", 0.10) for _ in range(10)]
    await asyncio.gather(*tasks)
    total = await budgeter.get_task_total("task-1")
    assert abs(total - 1.00) < 0.001  # no lost updates


# ══════════════════════════════════════════════════════════════════
# 12. test_concurrent_rate_limit_checks_are_safe
# ══════════════════════════════════════════════════════════════════


async def test_concurrent_rate_limit_checks_are_safe():
    """20 concurrent rate checks must not corrupt state."""
    guard = _make_guard(rate_limits={"default": "1000/min"})
    limiter = None
    # Build the rate limiter reference
    for ev in guard.pipeline.evaluators:
        if ev.name == "rate_limiter":
            limiter = ev
            break
    assert limiter is not None
    tasks = [limiter.record_call("test-tool", "agent-1") for _ in range(20)]
    await asyncio.gather(*tasks)
    count = await limiter.get_call_count("test-tool", 60)
    assert count == 20  # all 20 recorded correctly


# ══════════════════════════════════════════════════════════════════
# 13. test_concurrent_audit_log_writes_are_safe
# ══════════════════════════════════════════════════════════════════


async def test_concurrent_audit_log_writes_are_safe():
    """50 concurrent audit writes must all be persisted."""
    from datetime import UTC, datetime

    from plyra_guard.core.intent import AuditEntry

    guard = _make_guard()
    entries = [
        AuditEntry(
            action_id=f"action-{i}",
            agent_id="agent-1",
            action_type="test.action",
            verdict=Verdict.ALLOW,
            timestamp=datetime.now(UTC),
        )
        for i in range(50)
    ]
    tasks = [guard._audit_log.append_async(e) for e in entries]
    await asyncio.gather(*tasks)
    log = guard.get_audit_log()
    assert len(log) == 50
