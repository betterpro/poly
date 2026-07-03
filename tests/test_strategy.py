from datetime import UTC, datetime, timedelta

from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import Side, Trade
from polymarket_mm_bot.strategy import (
    REASON_PASSIVE,
    REASON_TOXIC_PULL,
    REASON_TOXIC_WIDEN,
    MarketMakingStrategy,
)


def _trade(price: float, size: float, side: Side | None, seconds_ago: float = 5.0) -> Trade:
    return Trade(
        market_id="m1",
        price=price,
        size=size,
        side=side,
        timestamp=datetime.now(UTC) - timedelta(seconds=seconds_ago),
    )


def test_strategy_builds_non_crossing_quotes(settings, book):
    strategy = MarketMakingStrategy(settings, InventoryManager(settings))
    signal = strategy.build_signal("m1", book, [])
    assert signal is not None
    assert signal.bid_price < signal.ask_price
    assert 0.01 <= signal.bid_price <= 0.99
    assert 0.01 <= signal.ask_price <= 0.99
    assert signal.reason == REASON_PASSIVE


def test_balanced_flow_keeps_passive_quotes(settings, book):
    strategy = MarketMakingStrategy(settings, InventoryManager(settings))
    trades = [
        _trade(0.50, 10, Side.BUY, seconds_ago=20),
        _trade(0.51, 10, Side.SELL, seconds_ago=15),
        _trade(0.50, 10, Side.BUY, seconds_ago=10),
        _trade(0.51, 10, Side.SELL, seconds_ago=5),
    ]
    signal = strategy.build_signal("m1", book, trades)
    assert signal is not None
    assert signal.reason == REASON_PASSIVE


def test_one_sided_flow_pulls_quotes(settings, book):
    strategy = MarketMakingStrategy(settings, InventoryManager(settings))
    trades = [_trade(0.51, 20, Side.BUY, seconds_ago=30 - i) for i in range(5)]
    signal = strategy.build_signal("m1", book, trades)
    assert signal is not None
    assert signal.reason == REASON_TOXIC_PULL
    assert signal.bid_price is None
    assert signal.ask_price is None
    assert signal.size == 0.0


def test_fast_price_drift_pulls_quotes(settings, book):
    strategy = MarketMakingStrategy(settings, InventoryManager(settings))
    # Balanced sides, but price ran 5 ticks inside the window.
    trades = [
        _trade(0.48, 10, Side.BUY, seconds_ago=25),
        _trade(0.49, 10, Side.SELL, seconds_ago=20),
        _trade(0.51, 10, Side.BUY, seconds_ago=15),
        _trade(0.52, 10, Side.SELL, seconds_ago=10),
        _trade(0.53, 10, Side.BUY, seconds_ago=5),
    ]
    signal = strategy.build_signal("m1", book, trades)
    assert signal is not None
    assert signal.reason == REASON_TOXIC_PULL


def test_moderate_imbalance_widens_spread_and_cuts_size(settings, book):
    strategy = MarketMakingStrategy(settings, InventoryManager(settings))
    baseline = strategy.build_signal("m1", book, [])
    trades = [
        _trade(0.51, 40, Side.BUY, seconds_ago=25),
        _trade(0.51, 40, Side.BUY, seconds_ago=20),
        _trade(0.51, 20, Side.SELL, seconds_ago=15),
    ]
    signal = strategy.build_signal("m1", book, trades)
    assert signal is not None
    assert signal.reason == REASON_TOXIC_WIDEN
    assert signal.size < baseline.size
    assert (signal.ask_price - signal.bid_price) > (baseline.ask_price - baseline.bid_price)


def test_stale_trades_are_ignored(settings, book):
    strategy = MarketMakingStrategy(settings, InventoryManager(settings))
    trades = [_trade(0.51, 20, Side.BUY, seconds_ago=600 + i) for i in range(5)]
    signal = strategy.build_signal("m1", book, trades)
    assert signal is not None
    assert signal.reason == REASON_PASSIVE


def test_side_inferred_from_midpoint_when_missing(settings, book):
    strategy = MarketMakingStrategy(settings, InventoryManager(settings))
    # No side info, but every trade printed above mid: buyer-initiated sweep.
    trades = [_trade(0.52, 20, None, seconds_ago=30 - i) for i in range(5)]
    signal = strategy.build_signal("m1", book, trades)
    assert signal is not None
    assert signal.reason == REASON_TOXIC_PULL
