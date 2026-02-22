"""
ActionGuard — Multi-Agent Orchestrator Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Shows an orchestrator with 3 sub-agents, trust levels,
delegation tracking, and one action getting escalated.
"""

from plyra_guard import ActionGuard, RiskLevel
from plyra_guard.config.loader import load_config_from_dict
from plyra_guard.exceptions import ExecutionBlockedError


def main() -> None:
    print("=" * 60)
    print("ActionGuard — Multi-Agent Orchestrator")
    print("=" * 60)

    config_data = {
        "global": {
            "max_delegation_depth": 3,
            "max_concurrent_delegations": 5,
        },
        "agents": [
            {
                "id": "orchestrator",
                "trust_level": 0.8,
                "can_delegate_to": [
                    "research-agent",
                    "code-agent",
                    "email-agent",
                ],
            },
            {"id": "research-agent", "trust_level": 0.6},
            {"id": "code-agent", "trust_level": 0.5},
            {"id": "email-agent", "trust_level": 0.3, "max_actions_per_run": 5},
        ],
        "policies": [
            {
                "name": "low_trust_email",
                "action_types": ["email.send"],
                "condition": "agent.trust_level < 0.4",
                "verdict": "WARN",
                "message": "Low trust agent sending email — proceed with caution",
            },
        ],
    }

    guard = ActionGuard(config=load_config_from_dict(config_data))
    guard._audit_log._exporters.clear()

    # Define tools for each sub-agent
    @guard.protect("web.search", risk_level=RiskLevel.LOW)
    def search_web(query: str) -> str:
        return f"[Research results for: {query}]"

    @guard.protect("code.generate", risk_level=RiskLevel.MEDIUM)
    def generate_code(spec: str) -> str:
        return f"def solution(): # Generated from: {spec}"

    @guard.protect("email.send", risk_level=RiskLevel.MEDIUM)
    def send_email(to: str, subject: str, body: str) -> bool:
        print(f"      → Email sent to {to}: {subject}")
        return True

    # Simulate orchestration
    print("\n── Orchestrator starts task ──")
    print()

    # 1. Research agent performs a search
    print("1. Research Agent: searching web...")
    guard._default_agent_id = "research-agent"
    try:
        result = search_web("best practices for AI safety")
        print(f"   ✓ {result}")
    except ExecutionBlockedError as e:
        print(f"   ✗ BLOCKED: {e.reason}")

    # 2. Code agent generates code
    print("\n2. Code Agent: generating code...")
    guard._default_agent_id = "code-agent"
    try:
        code = generate_code("AI safety middleware")
        print(f"   ✓ {code[:50]}...")
    except ExecutionBlockedError as e:
        print(f"   ✗ BLOCKED: {e.reason}")

    # 3. Email agent sends results (low trust — should get WARNING)
    print("\n3. Email Agent: sending results email...")
    guard._default_agent_id = "email-agent"
    try:
        send_email(
            to="boss@company.com",
            subject="AI Safety Report",
            body="Here are the findings...",
        )
        print("   ✓ Email sent (with WARNING logged)")
    except ExecutionBlockedError as e:
        print(f"   ✗ BLOCKED: {e.reason}")

    # 4. Show audit log
    print("\n── Audit Log ──")
    for entry in guard.get_audit_log():
        print(
            f"  [{entry.verdict.value:8s}] "
            f"agent={entry.agent_id:18s} "
            f"action={entry.action_type}"
        )

    # 5. Show metrics
    print("\n── Metrics ──")
    metrics = guard.get_metrics()
    print(f"  Total actions: {metrics.total_actions}")
    print(f"  Allowed: {metrics.allowed_actions}")
    print(f"  Warned: {metrics.warned_actions}")
    print(f"  Blocked: {metrics.blocked_actions}")

    print("\n" + "=" * 60)
    print("Done!")


if __name__ == "__main__":
    main()
