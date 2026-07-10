"""Inventory-risk control (tapered buying) and PnL time-series persistence."""

from __future__ import annotations

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.main import _buy_quote_size
from polymarket_mm_bot.models import Position


def _settings() -> Settings:
    return Settings(
        max_position_per_market=100,
        max_order_size=25,
        order_size=10,
        inventory_target_fraction=0.35,  # target = 35 shares
    )


def test_buy_full_size_when_flat():
    assert _buy_quote_size(_settings(), Position(market_id="m"), 10) == 10


def test_buy_tapers_as_inventory_grows():
    s = _settings()
    empty = _buy_quote_size(s, Position(market_id="m", yes_size=0), 10)
    half = _buy_quote_size(s, Position(market_id="m", yes_size=17.5), 10)  # half of target
    near = _buy_quote_size(s, Position(market_id="m", yes_size=31.5), 10)  # 90% of target
    assert empty > half > near > 0


def test_buy_stops_at_target():
    s = _settings()
    assert _buy_quote_size(s, Position(market_id="m", yes_size=35), 10) == 0.0
    assert _buy_quote_size(s, Position(market_id="m", yes_size=124.6), 10) == 0.0


def test_lower_fraction_caps_inventory_sooner():
    tight = Settings(max_position_per_market=100, max_order_size=25, order_size=10, inventory_target_fraction=0.2)
    # With a 20-share target, a 25-share position is already over the cap.
    assert _buy_quote_size(tight, Position(market_id="m", yes_size=25), 10) == 0.0


def test_pnl_snapshot_persists(tmp_path, monkeypatch):
    db = tmp_path / "pnl.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    from polymarket_mm_bot.config.settings import Settings as S
    from polymarket_mm_bot.config.settings import get_settings
    from polymarket_mm_bot.database.orm import Base, PnlSnapshotRow
    from polymarket_mm_bot.database.runtime_state import save_pnl_snapshot
    from polymarket_mm_bot.database.session import get_engine, get_session_factory

    get_settings.cache_clear()
    Base.metadata.create_all(get_engine())
    factory = get_session_factory(S())
    with factory() as session:
        save_pnl_snapshot(session, daily_pnl=1.5, total_pnl=8.4, unrealized_pnl=2.0, metadata={"bot_status": "paper_trading"})
    with factory() as session:
        rows = session.query(PnlSnapshotRow).all()
    assert len(rows) == 1
    assert rows[0].total_pnl == 8.4
    assert rows[0].daily_pnl == 1.5
    assert rows[0].unrealized_pnl == 2.0
