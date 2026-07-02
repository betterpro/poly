import pytest

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.database.orm import Base
from polymarket_mm_bot.database.runtime_state import save_order, save_position
from polymarket_mm_bot.database.session import get_engine, get_session_factory
from polymarket_mm_bot.models import BotOrder, Position, Side
from polymarket_mm_bot.trading_runtime import TradingRuntime


def test_live_mode_does_not_silently_use_paper_engine():
    settings = Settings(
        paper_trading=False,
        run_mode="live",
        live_trading_confirmed=True,
        polymarket_private_key="0xabc",
        polymarket_funder_address="0xdef",
    )
    with pytest.raises(RuntimeError, match="Live trading is not wired"):
        TradingRuntime(settings)


def test_runtime_reloads_persisted_orders_and_positions(tmp_path):
    db_path = tmp_path / "runtime.db"
    settings = Settings(database_url=f"sqlite:///{db_path}")
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = get_session_factory(settings)

    with session_factory() as session:
        save_order(
            session,
            BotOrder(
                client_order_id="paper-1",
                market_id="m1",
                token_id="yes-token",
                side=Side.BUY,
                price=0.5,
                size=10,
            ),
        )
        save_position(
            session,
            Position(market_id="m1", yes_size=10, avg_yes_price=0.5),
        )

    runtime = TradingRuntime(settings)
    assert "paper-1" in runtime.execution.orders
    assert runtime.inventory.get_position("m1").yes_size == 10
