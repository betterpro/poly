"""Profitability report computed from the bot's own tables.

Answers the question "is the edge real and worth scaling?" from orders, positions
and the pnl_snapshots time-series. DB-agnostic (grouping is done in Python) so it
runs against Postgres in production and sqlite in tests.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from polymarket_mm_bot.database.orm import BotOrderRow, PnlSnapshotRow, PositionRow, RiskEventRow


def _as_date(value: datetime | None) -> date | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).date()


def build_report(session: Session, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)

    orders = session.query(BotOrderRow).all()
    positions = session.query(PositionRow).all()
    snapshots = sorted(session.query(PnlSnapshotRow).all(), key=lambda r: r.timestamp or now)
    risk_events = session.query(RiskEventRow).all()

    orders_total = len(orders)
    filled = [o for o in orders if (o.filled_size or 0) > 0]
    fills = len(filled)
    filled_shares = sum(o.filled_size or 0 for o in filled)
    fill_rate = fills / orders_total if orders_total else 0.0

    realized_pnl = sum(p.realized_pnl or 0 for p in positions)
    avg_edge_per_fill = realized_pnl / fills if fills else 0.0

    # Open inventory / concentration risk.
    per_market_exposure = {
        p.market_id: abs((p.yes_size or 0) * (p.avg_yes_price or 0))
        + abs((p.no_size or 0) * (p.avg_no_price or 0))
        for p in positions
        if (p.yes_size or 0) > 0 or (p.no_size or 0) > 0
    }
    open_exposure = sum(per_market_exposure.values())
    top_exposure = max(per_market_exposure.values(), default=0.0)
    concentration = top_exposure / open_exposure if open_exposure else 0.0
    open_markets = len(per_market_exposure)

    # Fills per day (activity trend), last 7 days.
    fills_by_day: dict[date, int] = defaultdict(int)
    for o in filled:
        day = _as_date(o.updated_at)
        if day is not None:
            fills_by_day[day] += 1
    recent_days = sorted(fills_by_day)[-7:]
    fills_per_day = {d.isoformat(): fills_by_day[d] for d in recent_days}
    avg_fills_per_day = sum(fills_by_day.values()) / len(fills_by_day) if fills_by_day else 0.0

    # PnL curve from snapshots: last total_pnl of each day, then day-over-day deltas.
    last_total_by_day: dict[date, float] = {}
    latest_unrealized = 0.0
    latest_total = 0.0
    for s in snapshots:
        day = _as_date(s.timestamp)
        if day is not None:
            last_total_by_day[day] = s.total_pnl or 0.0
        latest_unrealized = s.unrealized_pnl or 0.0
        latest_total = s.total_pnl or 0.0
    pnl_days = sorted(last_total_by_day)
    daily_deltas = [last_total_by_day[b] - last_total_by_day[a] for a, b in zip(pnl_days, pnl_days[1:])]
    avg_daily_pnl = sum(daily_deltas) / len(daily_deltas) if daily_deltas else None
    best_day = max(daily_deltas, default=None)
    worst_day = min(daily_deltas, default=None)
    winning_days = sum(1 for d in daily_deltas if d > 0)

    daily_return_pct = None
    if avg_daily_pnl is not None and open_exposure > 0:
        daily_return_pct = avg_daily_pnl / open_exposure * 100

    risk_counts: dict[str, int] = defaultdict(int)
    for e in risk_events:
        day = _as_date(e.timestamp)
        if day is None or (now.date() - day).days <= 7:
            risk_counts[e.code] += 1

    # Verdict: is the sample big enough to trust, and is the edge positive?
    if fills < 100 or len(daily_deltas) < 3:
        verdict = "insufficient_sample"
    elif avg_daily_pnl is not None and avg_daily_pnl > 0 and winning_days >= len(daily_deltas) * 0.6:
        verdict = "edge_positive"
    elif avg_daily_pnl is not None and avg_daily_pnl < 0:
        verdict = "edge_negative"
    else:
        verdict = "inconclusive"

    return {
        "orders_total": orders_total,
        "fills": fills,
        "fill_rate": fill_rate,
        "filled_shares": filled_shares,
        "realized_pnl": realized_pnl,
        "avg_edge_per_fill": avg_edge_per_fill,
        "unrealized_pnl": latest_unrealized,
        "total_pnl": latest_total if snapshots else realized_pnl,
        "open_exposure": open_exposure,
        "open_markets": open_markets,
        "concentration": concentration,
        "avg_fills_per_day": avg_fills_per_day,
        "fills_per_day": fills_per_day,
        "pnl_days_tracked": len(pnl_days),
        "avg_daily_pnl": avg_daily_pnl,
        "best_day": best_day,
        "worst_day": worst_day,
        "winning_days": winning_days,
        "daily_return_pct": daily_return_pct,
        "risk_events_7d": dict(risk_counts),
        "verdict": verdict,
    }


def _money(value) -> str:
    if value is None:
        return "n/a"
    return f"${value:,.2f}"


def format_report(report: dict) -> str:
    lines: list[str] = []
    a = lines.append
    a("=== Polymarket MM — profitability report ===")
    a("")
    a("ACTIVITY")
    a(f"  orders placed .......... {report['orders_total']:,}")
    a(f"  fills .................. {report['fills']:,}  ({report['fill_rate'] * 100:.1f}% fill rate)")
    a(f"  shares filled .......... {report['filled_shares']:,.1f}")
    a(f"  avg fills / day ........ {report['avg_fills_per_day']:.1f}")
    if report["fills_per_day"]:
        recent = "  ".join(f"{d}:{n}" for d, n in report["fills_per_day"].items())
        a(f"  recent (day:fills) ..... {recent}")
    a("")
    a("PROFIT & LOSS")
    a(f"  realized PnL ........... {_money(report['realized_pnl'])}  (lifetime, closed trades)")
    a(f"  unrealized PnL ......... {_money(report['unrealized_pnl'])}  (open positions)")
    a(f"  total PnL .............. {_money(report['total_pnl'])}")
    a(f"  edge per fill .......... {_money(report['avg_edge_per_fill'])}")
    if report["avg_daily_pnl"] is not None:
        a(f"  avg PnL / day .......... {_money(report['avg_daily_pnl'])}  over {report['pnl_days_tracked']} tracked day(s)")
        a(f"  best / worst day ....... {_money(report['best_day'])} / {_money(report['worst_day'])}")
        a(f"  winning days ........... {report['winning_days']}/{max(report['pnl_days_tracked'] - 1, 0)}")
    else:
        a("  avg PnL / day .......... n/a (need >= 2 days of pnl_snapshots)")
    if report["daily_return_pct"] is not None:
        a(f"  daily return on capital  {report['daily_return_pct']:.2f}% of open exposure")
    a("")
    a("RISK / CAPITAL")
    a(f"  open exposure .......... {_money(report['open_exposure'])} across {report['open_markets']} market(s)")
    a(f"  concentration .......... {report['concentration'] * 100:.0f}% in the single largest market")
    if report["risk_events_7d"]:
        events = ", ".join(f"{k}={v}" for k, v in sorted(report["risk_events_7d"].items(), key=lambda kv: -kv[1]))
        a(f"  risk events (7d) ....... {events}")
    a("")
    verdicts = {
        "insufficient_sample": "NOT ENOUGH DATA yet — keep running. Need >=100 fills and >=3 days of PnL history before trusting the edge.",
        "edge_positive": "EDGE LOOKS POSITIVE — steady up days. Candidate for careful, gradual scaling (more markets/size, risk caps intact).",
        "edge_negative": "EDGE IS NEGATIVE — average day loses money. Do NOT add capital; fix the strategy first.",
        "inconclusive": "INCONCLUSIVE — flat/choppy. Let it run longer before scaling.",
    }
    a(f"VERDICT: {verdicts.get(report['verdict'], report['verdict'])}")
    return "\n".join(lines)
