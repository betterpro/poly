from datetime import UTC, datetime, timedelta

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.database.orm import Base, TradeRow
from polymarket_mm_bot.reporting.optimizer import build_optimizer_controls


def test_optimizer_controls_block_losers_and_scale_winners(tmp_path, monkeypatch):
    db = tmp_path / "optimizer-controls.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    from polymarket_mm_bot.config.settings import Settings as S
    from polymarket_mm_bot.config.settings import get_settings
    from polymarket_mm_bot.database.session import get_engine, get_session_factory

    get_settings.cache_clear()
    Base.metadata.create_all(get_engine())
    factory = get_session_factory(S())
    now = datetime(2026, 7, 21, tzinfo=UTC)
    with factory() as session:
        session.add_all(
            [
                TradeRow(order_id="wb1", market_id="winner", side="buy", price=0.40, size=10, timestamp=now),
                TradeRow(order_id="ws1", market_id="winner", side="sell", price=0.46, size=5, timestamp=now + timedelta(minutes=1)),
                TradeRow(order_id="ws2", market_id="winner", side="sell", price=0.47, size=5, timestamp=now + timedelta(minutes=2)),
                TradeRow(order_id="wb2", market_id="winner", side="buy", price=0.41, size=1, timestamp=now + timedelta(minutes=3)),
                TradeRow(order_id="lb1", market_id="loser", side="buy", price=0.60, size=10, timestamp=now),
                TradeRow(order_id="ls1", market_id="loser", side="sell", price=0.48, size=5, timestamp=now + timedelta(minutes=1)),
                TradeRow(order_id="ls2", market_id="loser", side="sell", price=0.47, size=5, timestamp=now + timedelta(minutes=2)),
                TradeRow(order_id="lb2", market_id="loser", side="buy", price=0.59, size=1, timestamp=now + timedelta(minutes=3)),
            ]
        )
        session.commit()
        controls = build_optimizer_controls(session, Settings())

    assert controls["scaled_market_ids"] == ["winner"]
    assert controls["blocked_market_ids"] == ["loser"]


def test_optimizer_controls_can_be_disabled(tmp_path, monkeypatch):
    db = tmp_path / "optimizer-disabled.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    from polymarket_mm_bot.config.settings import Settings as S
    from polymarket_mm_bot.config.settings import get_settings
    from polymarket_mm_bot.database.session import get_engine, get_session_factory

    get_settings.cache_clear()
    Base.metadata.create_all(get_engine())
    factory = get_session_factory(S())
    with factory() as session:
        controls = build_optimizer_controls(session, Settings(optimizer_auto_enabled=False))

    assert controls["scaled_market_ids"] == []
    assert controls["blocked_market_ids"] == []
