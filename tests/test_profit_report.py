from __future__ import annotations

from datetime import UTC, datetime, timedelta

from polymarket_mm_bot.database.orm import Base, BotOrderRow, PnlSnapshotRow, PositionRow, RiskEventRow
from polymarket_mm_bot.reporting.profit_report import build_report, format_report


def _session(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{(tmp_path / 'r.db').as_posix()}")
    from polymarket_mm_bot.config.settings import Settings, get_settings
    from polymarket_mm_bot.database.session import get_engine, get_session_factory

    get_settings.cache_clear()
    Base.metadata.create_all(get_engine())
    return get_session_factory(Settings())()


def test_report_on_empty_db(tmp_path, monkeypatch):
    with _session(tmp_path, monkeypatch) as session:
        report = build_report(session)
    assert report["orders_total"] == 0
    assert report["fills"] == 0
    assert report["verdict"] == "insufficient_sample"
    # Formatting must not crash on empty data.
    assert "profitability report" in format_report(report).lower()


def test_report_matches_seeded_activity(tmp_path, monkeypatch):
    now = datetime(2026, 7, 10, tzinfo=UTC)
    with _session(tmp_path, monkeypatch) as session:
        # 10 orders, 4 of them filled.
        for i in range(10):
            session.add(
                BotOrderRow(
                    client_order_id=f"o{i}",
                    market_id="m1",
                    side="buy",
                    outcome="YES",
                    price=0.8,
                    size=10,
                    filled_size=5 if i < 4 else 0,
                    status="filled" if i < 4 else "open",
                    updated_at=now - timedelta(hours=1),
                )
            )
        session.add(PositionRow(market_id="m1", yes_size=124.6, avg_yes_price=0.79, realized_pnl=8.38))
        session.add(PositionRow(market_id="m2", yes_size=8.16, avg_yes_price=0.85, realized_pnl=0.0))
        session.add(RiskEventRow(market_id=None, code="stale_market_data", message="x", metadata_json={}))
        session.commit()
        report = build_report(session, now=now)

    assert report["orders_total"] == 10
    assert report["fills"] == 4
    assert abs(report["fill_rate"] - 0.4) < 1e-9
    assert abs(report["realized_pnl"] - 8.38) < 1e-6
    assert abs(report["avg_edge_per_fill"] - 8.38 / 4) < 1e-6
    # m1 dominates exposure -> high concentration.
    assert report["concentration"] > 0.9
    assert report["open_markets"] == 2
    assert report["risk_events_7d"].get("stale_market_data") == 1
    assert report["verdict"] == "insufficient_sample"  # <100 fills


def test_report_flags_positive_edge_with_enough_data(tmp_path, monkeypatch):
    now = datetime(2026, 7, 10, tzinfo=UTC)
    with _session(tmp_path, monkeypatch) as session:
        for i in range(150):
            session.add(
                BotOrderRow(
                    client_order_id=f"o{i}",
                    market_id="m1",
                    side="buy",
                    outcome="YES",
                    price=0.5,
                    size=10,
                    filled_size=5,
                    status="filled",
                    updated_at=now - timedelta(days=i % 5),
                )
            )
        session.add(PositionRow(market_id="m1", yes_size=10, avg_yes_price=0.5, realized_pnl=50.0))
        # 5 days of steadily rising total_pnl.
        for d in range(5):
            session.add(
                PnlSnapshotRow(
                    timestamp=now - timedelta(days=4 - d),
                    daily_pnl=10.0,
                    total_pnl=10.0 * d,
                    unrealized_pnl=1.0,
                    metadata_json={},
                )
            )
        session.commit()
        report = build_report(session, now=now)

    assert report["pnl_days_tracked"] == 5
    assert report["avg_daily_pnl"] == 10.0
    assert report["winning_days"] == 4
    assert report["verdict"] == "edge_positive"
    assert "EDGE LOOKS POSITIVE" in format_report(report)
