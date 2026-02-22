"""
Dashboard Metrics
~~~~~~~~~~~~~~~~~

Pure-function metric aggregation and SVG chart generation
for the plyra-guard dashboard.  All data is read from the
existing AuditLog — no additional storage is introduced.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from plyra_guard.core.verdict import Verdict

if TYPE_CHECKING:
    from plyra_guard.observability.audit_log import AuditLog

__all__ = [
    "StatCards",
    "MinuteBucket",
    "AgentRow",
    "FeedRow",
    "DashboardMetrics",
    "generate_chart_svg",
]


# ── Dataclasses ──────────────────────────────────────────────


@dataclass
class StatCards:
    """Aggregate stat-card data for the dashboard header."""

    total_actions: int = 0
    total_blocked: int = 0
    blocked_pct: float = 0.0
    total_escalated: int = 0
    escalated_pct: float = 0.0
    avg_risk_score: float = 0.0
    delta_5min: int = 0
    delta_blocked_5min: int = 0


@dataclass
class MinuteBucket:
    """One-minute time bucket for the block-rate chart."""

    minute: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )
    allow_count: int = 0
    block_count: int = 0
    escalate_count: int = 0


@dataclass
class AgentRow:
    """Per-agent breakdown row for the agent table."""

    agent_id: str = ""
    trust_level: float = 0.0
    total_actions: int = 0
    blocked_count: int = 0
    blocked_pct: float = 0.0
    budget_used: float = 0.0
    budget_total: float = 0.0
    budget_pct: float = 0.0
    over_budget: bool = False
    last_action_at: datetime | None = None
    is_active: bool = False


@dataclass
class FeedRow:
    """One row in the live action feed."""

    action_id: str = ""
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(UTC),
    )
    agent_id: str = ""
    action_type: str = ""
    verdict: Verdict = Verdict.ALLOW
    risk_score: float = 0.0
    policy_triggered: str | None = None
    has_rollback: bool = False
    rolled_back: bool = False


# ── DashboardMetrics ─────────────────────────────────────────


class DashboardMetrics:
    """Read-only metric aggregation backed by an AuditLog."""

    def __init__(self, audit_log: AuditLog) -> None:
        self._audit = audit_log

    # -- public API ------------------------------------------

    def get_stats(self) -> StatCards:
        """Return aggregate stat-card numbers."""
        entries = self._audit.query()
        total = len(entries)
        if total == 0:
            return StatCards()

        blocked = sum(1 for e in entries if e.verdict == Verdict.BLOCK)
        escalated = sum(1 for e in entries if e.verdict == Verdict.ESCALATE)
        risk_sum = sum(e.risk_score for e in entries)

        now = datetime.now(UTC)
        cutoff = now - timedelta(minutes=5)
        recent = [e for e in entries if e.timestamp >= cutoff]
        delta_5 = len(recent)
        delta_b5 = sum(1 for e in recent if e.verdict == Verdict.BLOCK)

        return StatCards(
            total_actions=total,
            total_blocked=blocked,
            blocked_pct=round(blocked / total * 100, 1) if total else 0.0,
            total_escalated=escalated,
            escalated_pct=round(escalated / total * 100, 1) if total else 0.0,
            avg_risk_score=round(risk_sum / total, 2),
            delta_5min=delta_5,
            delta_blocked_5min=delta_b5,
        )

    def get_chart_data(self) -> list[MinuteBucket]:
        """Return 60 one-minute buckets for the last hour."""
        now = datetime.now(UTC)
        buckets: dict[int, MinuteBucket] = {}
        for i in range(60):
            m = now - timedelta(minutes=59 - i)
            key = int(m.timestamp()) // 60
            buckets[key] = MinuteBucket(
                minute=m.replace(second=0, microsecond=0),
            )

        cutoff = now - timedelta(minutes=60)
        for entry in self._audit.query():
            if entry.timestamp < cutoff:
                continue
            key = int(entry.timestamp.timestamp()) // 60
            if key not in buckets:
                continue
            b = buckets[key]
            if entry.verdict == Verdict.BLOCK:
                b.block_count += 1
            elif entry.verdict == Verdict.ESCALATE:
                b.escalate_count += 1
            else:
                b.allow_count += 1

        return [buckets[k] for k in sorted(buckets.keys())]

    def get_agent_breakdown(self) -> list[AgentRow]:
        """Return per-agent stats for the agent table."""
        entries = self._audit.query()
        agents: dict[str, AgentRow] = {}
        now = datetime.now(UTC)

        for entry in entries:
            if entry.agent_id not in agents:
                agents[entry.agent_id] = AgentRow(
                    agent_id=entry.agent_id,
                )
            row = agents[entry.agent_id]
            row.total_actions += 1
            if entry.verdict == Verdict.BLOCK:
                row.blocked_count += 1
            row.last_action_at = entry.timestamp

        for row in agents.values():
            if row.total_actions:
                row.blocked_pct = round(
                    row.blocked_count / row.total_actions * 100,
                    1,
                )
            if row.last_action_at:
                row.is_active = (now - row.last_action_at).total_seconds() < 60

        return sorted(
            agents.values(),
            key=lambda r: r.total_actions,
            reverse=True,
        )

    def get_recent_feed(
        self,
        limit: int = 50,
    ) -> list[FeedRow]:
        """Return the most recent *limit* feed rows."""
        entries = self._audit.query()
        # newest first
        entries = sorted(
            entries,
            key=lambda e: e.timestamp,
            reverse=True,
        )[:limit]
        return [
            FeedRow(
                action_id=e.action_id,
                timestamp=e.timestamp,
                agent_id=e.agent_id,
                action_type=e.action_type,
                verdict=e.verdict,
                risk_score=e.risk_score,
                policy_triggered=e.policy_triggered,
                has_rollback=False,
                rolled_back=e.rolled_back,
            )
            for e in entries
        ]


# ── SVG chart generator (pure function) ──────────────────────


def generate_chart_svg(
    buckets: list[MinuteBucket],
) -> str:
    """Generate an SVG bar chart from minute-buckets.

    Returns a complete ``<svg>`` string with viewBox 0 0 900 200.
    No external dependencies — pure string building.
    """
    vw, vh = 900, 200
    pad_left, pad_bottom = 40, 24
    chart_w = vw - pad_left - 10
    chart_h = vh - 30 - pad_bottom
    bar_w = 12
    gap = max(
        1,
        (chart_w - len(buckets) * bar_w) // max(len(buckets), 1),
    )
    step = bar_w + gap

    max_count = max(
        (b.allow_count + b.block_count + b.escalate_count for b in buckets),
        default=1,
    )
    max_count = max(max_count, 1)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg"'
        f' viewBox="0 0 {vw} {vh}"'
        f' style="width:100%;background:#0d1525;'
        f'border-radius:8px">',
    ]

    # Title
    parts.append(
        '<text x="50" y="18"'
        ' fill="#4a7a9b"'
        ' font-family="Courier New,monospace"'
        ' font-size="10"'
        ' letter-spacing="3">'
        "BLOCK RATE \u00b7 LAST 60 MIN</text>"
    )

    # Grid lines
    for i in range(5):
        y = 30 + int(chart_h * i / 4)
        parts.append(
            f'<line x1="{pad_left}" y1="{y}"'
            f' x2="{vw - 10}" y2="{y}"'
            f' stroke="#1a3050" opacity="0.4"/>'
        )
        val = int(max_count * (4 - i) / 4)
        parts.append(
            f'<text x="4" y="{y + 3}"'
            f' fill="#4a7a9b"'
            f' font-family="Courier New,monospace"'
            f' font-size="9">{val}</text>'
        )

    # Bars
    for idx, b in enumerate(buckets):
        x = pad_left + idx * step
        total = b.allow_count + b.block_count + b.escalate_count

        if total == 0:
            # faint placeholder bar
            parts.append(
                f'<rect x="{x}" y="{30 + chart_h - 2}"'
                f' width="{bar_w}" height="2"'
                f' fill="#1a3050"/>'
            )
        else:
            # allow portion
            allow_h = int(b.allow_count / max_count * chart_h)
            block_h = int(b.block_count / max_count * chart_h)
            esc_h = int(b.escalate_count / max_count * chart_h)
            stacked = allow_h + block_h + esc_h
            base_y = 30 + chart_h - stacked

            if allow_h:
                parts.append(
                    f'<rect x="{x}" y="{base_y + block_h + esc_h}"'
                    f' width="{bar_w}" height="{allow_h}"'
                    f' fill="#00cc88" opacity="0.3"/>'
                )
            if esc_h:
                parts.append(
                    f'<rect x="{x}" y="{base_y + block_h}"'
                    f' width="{bar_w}" height="{esc_h}"'
                    f' fill="#ffaa00" opacity="0.5"/>'
                )
            if block_h:
                parts.append(
                    f'<rect x="{x}" y="{base_y}"'
                    f' width="{bar_w}" height="{block_h}"'
                    f' fill="#ff4444" opacity="0.7"/>'
                )

        # X-axis labels every 10 bars
        if idx % 10 == 0:
            label = b.minute.strftime("%H:%M")
            parts.append(
                f'<text x="{x}" y="{vh - 6}"'
                f' fill="#4a7a9b"'
                f' font-family="Courier New,monospace"'
                f' font-size="9">'
                f"{html.escape(label)}</text>"
            )

    parts.append("</svg>")
    return "\n".join(parts)
