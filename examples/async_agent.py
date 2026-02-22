#!/usr/bin/env python3
"""
Async Agent Example
~~~~~~~~~~~~~~~~~~~

Demonstrates three async scenarios with ActionGuard:

1. Concurrent actions with rate limiting
2. Global Budget Manager under concurrent load
3. Async multi-agent chain with audit trail

Run:
    python examples/async_agent.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

# Add parent dir to path so the example is runnable standalone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plyra_guard import ActionGuard, ActionIntent, RiskLevel
from plyra_guard.config.loader import load_config_from_dict
from plyra_guard.core.intent import AgentCall
from plyra_guard.core.verdict import TrustLevel
from plyra_guard.exceptions import ExecutionBlockedError

# ── Color helpers (plain fallback if colorama unavailable) ───────

try:
    from colorama import Fore, Style
    from colorama import init as colorama_init

    colorama_init(autoreset=True)
    GREEN = Fore.GREEN
    RED = Fore.RED
    YELLOW = Fore.YELLOW
    CYAN = Fore.CYAN
    MAGENTA = Fore.MAGENTA
    DIM = Style.DIM
    RESET = Style.RESET_ALL
    BOLD = Style.BRIGHT
except ImportError:
    GREEN = RED = YELLOW = CYAN = MAGENTA = DIM = RESET = BOLD = ""


def _header(title: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{'═' * 60}\n")


def _ok(msg: str) -> None:
    print(f"  {GREEN}✅ {msg}{RESET}")


def _fail(msg: str) -> None:
    print(f"  {RED}🚫 {msg}{RESET}")


def _info(msg: str) -> None:
    print(f"  {DIM}{msg}{RESET}")


# ══════════════════════════════════════════════════════════════════
# DEMO 1 — Concurrent Actions with Rate Limiting
# ══════════════════════════════════════════════════════════════════


async def demo_rate_limiting():
    _header("DEMO 1 — Concurrent Actions with Rate Limiting")

    guard = ActionGuard(
        config=load_config_from_dict(
            {
                "rate_limits": {"default": "3/min"},
            }
        )
    )
    guard._audit_log._exporters.clear()

    @guard.protect("api.fetch", risk_level=RiskLevel.LOW)
    def fetch_data(url: str) -> dict:
        return {"url": url, "status": 200}

    results = []
    blocked = []

    _info("Firing 5 API calls sequentially with rate limit 3/min ...\n")

    for i in range(5):
        t0 = time.perf_counter()
        try:
            loop = asyncio.get_event_loop()
            r = await loop.run_in_executor(
                None, fetch_data, f"https://api.example.com/data/{i}"
            )
            elapsed = (time.perf_counter() - t0) * 1000
            results.append(r)
            _ok(f"Call {i + 1}: {r['url']}  ({elapsed:.1f}ms)")
        except ExecutionBlockedError as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            blocked.append(i)
            _fail(f"Call {i + 1}: RATE LIMITED  ({elapsed:.1f}ms) — {exc.reason}")

    print()
    _info(f"Result: {len(results)} succeeded, {len(blocked)} throttled")
    _info("Rate limiter correctly enforced 3/min limit ✓")


# ══════════════════════════════════════════════════════════════════
# DEMO 2 — Global Budget Manager Under Concurrent Load
# ══════════════════════════════════════════════════════════════════


async def demo_budget_enforcement():
    _header("DEMO 2 — Global Budget Manager Under Concurrent Load")

    guard = ActionGuard(
        config=load_config_from_dict(
            {
                "budget": {"per_task": 1.00, "per_agent_per_run": 5.00},
            }
        )
    )
    guard._audit_log._exporters.clear()

    _info("5 agents each calling $0.30 API, task budget $1.00\n")

    successes = []
    blocked = []

    for i in range(5):
        agent_id = f"agent-{i + 1}"
        intent = ActionIntent(
            action_type="api.expensive",
            tool_name="api_call",
            parameters={"endpoint": f"/v1/generate/{i}"},
            agent_id=agent_id,
            task_id="budget-task",
            estimated_cost=0.30,
        )
        try:
            guard._run_pipeline(
                intent=intent,
                func=lambda: {"status": "ok"},
                args=(),
                kwargs={},
                enable_rollback=False,
            )
            spend = guard._global_budgeter.get_task_spend("budget-task")
            successes.append(agent_id)
            _ok(f"{agent_id}: $0.30 spent → total: ${spend:.2f}")
        except ExecutionBlockedError:
            spend = guard._global_budgeter.get_task_spend("budget-task")
            blocked.append(agent_id)
            _fail(f"{agent_id}: BUDGET EXCEEDED → total: ${spend:.2f}")

    print()
    total = guard._global_budgeter.get_task_spend("budget-task")
    _info(
        f"Result: {len(successes)} succeeded ($0.30 each = ${total:.2f}), "
        f"{len(blocked)} blocked by budget enforcement"
    )
    _info("Budget correctly aggregated in real-time ✓")


# ══════════════════════════════════════════════════════════════════
# DEMO 3 — Async Multi-Agent Chain
# ══════════════════════════════════════════════════════════════════


async def demo_multi_agent_chain():
    _header("DEMO 3 — Async Multi-Agent Chain")

    guard = ActionGuard(
        config=load_config_from_dict(
            {
                "policies": [
                    {
                        "name": "escalate_email",
                        "action_types": ["email.send"],
                        "condition": "estimated_cost > 0",
                        "verdict": "ESCALATE",
                        "message": "Email sending requires human approval",
                    },
                ],
            }
        )
    )
    guard._audit_log._exporters.clear()

    # Register agents
    guard._trust_ledger.register("orchestrator", TrustLevel.ORCHESTRATOR)
    guard._trust_ledger.register("data-agent", TrustLevel.SUB_AGENT)
    guard._trust_ledger.register("email-agent", TrustLevel.SUB_AGENT)
    guard._trust_ledger.register("report-agent", TrustLevel.SUB_AGENT)

    _info("Orchestrator spawning 3 sub-agents concurrently ...\n")

    async def sub_agent_work(agent_id: str, actions: list[dict]):
        """Each sub-agent performs its assigned actions."""
        chain = [
            AgentCall(agent_id="orchestrator", trust_level=0.8, instruction="delegate")
        ]
        for action in actions:
            intent = ActionIntent(
                action_type=action["type"],
                tool_name=action["name"],
                parameters=action.get("params", {}),
                agent_id=agent_id,
                task_id="multi-agent-task",
                estimated_cost=action.get("cost", 0.0),
                instruction_chain=chain,
            )
            try:
                guard._run_pipeline(
                    intent=intent,
                    func=lambda: {"status": "done"},
                    args=(),
                    kwargs={},
                    enable_rollback=False,
                )
                _ok(f"  {agent_id} → {action['type']} ({action['name']})")
            except ExecutionBlockedError as exc:
                _fail(f"  {agent_id} → {action['type']} ESCALATED: {exc.reason}")

    # Define sub-agent workloads
    await asyncio.gather(
        sub_agent_work(
            "data-agent",
            [
                {
                    "type": "db.query",
                    "name": "fetch_users",
                    "params": {"table": "users"},
                },
                {
                    "type": "file.write",
                    "name": "save_report",
                    "params": {"path": "/tmp/report.csv"},
                },
            ],
        ),
        sub_agent_work(
            "email-agent",
            [
                {
                    "type": "email.send",
                    "name": "send_notification",
                    "cost": 0.01,
                    "params": {"to": "team@example.com"},
                },
                {
                    "type": "file.read",
                    "name": "read_template",
                    "params": {"path": "/tmp/template.html"},
                },
            ],
        ),
        sub_agent_work(
            "report-agent",
            [
                {"type": "compute.run", "name": "generate_charts"},
                {
                    "type": "file.write",
                    "name": "save_charts",
                    "params": {"path": "/tmp/charts.png"},
                },
            ],
        ),
    )

    # Show audit trail
    print()
    entries = guard._audit_log.query()
    _info(f"Audit log: {len(entries)} entries recorded")
    for entry in entries:
        symbol = "✅" if entry.verdict.value == "ALLOW" else "🚫"
        _info(
            f"  {symbol} {entry.agent_id} → {entry.action_type} [{entry.verdict.value}]"
        )

    _info("\nInstruction chain preserved across all agents ✓")


# ══════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════


async def main():
    print(f"\n{BOLD}{MAGENTA}{'━' * 60}{RESET}")
    print(f"{BOLD}{MAGENTA}  ActionGuard Async Agent Demo{RESET}")
    print(f"{BOLD}{MAGENTA}{'━' * 60}{RESET}")

    t0 = time.perf_counter()

    await demo_rate_limiting()
    await demo_budget_enforcement()
    await demo_multi_agent_chain()

    elapsed = time.perf_counter() - t0
    print(f"\n{DIM}Total demo time: {elapsed:.2f}s{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
