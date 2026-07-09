from datetime import UTC, datetime, timedelta

from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import BookLevel, OrderBook, Side, Trade
from polymarket_mm_bot.strategy import (
    REASON_DOWNTREND_EXIT,
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
    assert signal.bid_price <= book.best_bid
    assert signal.ask_price >= book.best_ask
    assert 0.01 <= signal.bid_price <= 0.99
    assert 0.01 <= signal.ask_price <= 0.99
    assert signal.reason == REASON_PASSIVE


def test_strategy_never_crosses_one_tick_spread(settings):
    book = OrderBook(
        market_id="m1",
        token_id="yes-token",
        bids=[BookLevel(price=0.12, size=5000)],
        asks=[BookLevel(price=0.13, size=5000)],
    )
    strategy = MarketMakingStrategy(settings, InventoryManager(settings))
    signal = strategy.build_signal("m1", book, [])
    assert signal is not None
    assert signal.bid_price == 0.12
    assert signal.ask_price == 0.14


def test_fair_price_ignores_other_token_trades(settings):
    book = OrderBook(
        market_id="m1",
        token_id="yes-token",
        bids=[BookLevel(price=0.12, size=5000)],
        asks=[BookLevel(price=0.13, size=5000)],
    )
    trades = [
        Trade(
            market_id="m1",
            token_id="no-token",
            price=0.88,
            size=100,
            side=Side.BUY,
            timestamp=datetime.now(UTC) - timedelta(seconds=5),
        )
        for _ in range(5)
    ]
    strategy = MarketMakingStrategy(settings, InventoryManager(settings))
    signal = strategy.build_signal("m1", book, trades)
    assert signal is not None
    assert signal.fair_price in {0.12, 0.13}
    assert signal.ask_price == 0.14


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


def test_long_inventory_reduces_bid_without_crossing_ask(settings, book):
    inventory = InventoryManager(settings)
    inventory.get_position("m1").yes_size = settings.max_position_per_market
    strategy = MarketMakingStrategy(settings, inventory)
    flat_signal = MarketMakingStrategy(settings, InventoryManager(settings)).build_signal("m1", book, [])
    long_signal = strategy.build_signal("m1", book, [])
    assert flat_signal is not None
    assert long_signal is not None
    assert long_signal.bid_price < flat_signal.bid_price
    assert long_signal.ask_price >= book.best_ask


def test_stale_trades_are_ignored(settings, book):
    strategy = MarketMakingStrategy(settings, InventoryManager(settings))
    trades = [_trade(0.51, 20, Side.BUY, seconds_ago=600 + i) for i in range(5)]
    signal = strategy.build_signal("m1", book, trades)
    assert signal is not None
    assert signal.reason == REASON_PASSIVE


def test_sub_tick_longshot_book_is_not_quoted(settings):
    from polymarket_mm_bot.models import BookLevel, OrderBook

    strategy = MarketMakingStrategy(settings, InventoryManager(settings))
    # Real longshot books trade below one tick (e.g. 0.008/0.009). The 0.01
    # price clamp would turn our bid into an instant taker fill above the ask.
    book = OrderBook(
        market_id="m1",
        token_id="yes-token",
        bids=[BookLevel(price=0.008, size=5000)],
        asks=[BookLevel(price=0.009, size=5000)],
    )
    assert strategy.build_signal("m1", book, []) is None


def test_side_inferred_from_midpoint_when_missing(settings, book):
    strategy = MarketMakingStrategy(settings, InventoryManager(settings))
    # No side info, but every trade printed above mid: buyer-initiated sweep.
    trades = [_trade(0.52, 20, None, seconds_ago=30 - i) for i in range(5)]
    signal = strategy.build_signal("m1", book, trades)
    assert signal is not None
    assert signal.reason == REASON_TOXIC_PULL


def test_microprice_leans_toward_heavy_bid_side(settings):
    book = OrderBook(
        market_id="m1",
        token_id="yes-token",
        bids=[BookLevel(price=0.49, size=900)],
        asks=[BookLevel(price=0.52, size=100)],
    )
    strategy = MarketMakingStrategy(settings, InventoryManager(settings))
    fair = strategy.estimate_fair_price(book)
    midpoint = (0.49 + 0.52) / 2
    assert fair is not None
    assert fair > midpoint
    assert 0.49 <= fair <= 0.52


def test_mild_downtrend_pauses_bid_but_keeps_ask(settings, book):
    inventory = InventoryManager(settings)
    inventory.get_position("m1").yes_size = 10
    strategy = MarketMakingStrategy(settings, inventory)
    # Balanced buy/sell volume (no toxic imbalance) but price drifted two
    # ticks lower inside the window: stop buying, keep quoting the exit.
    trades = [
        _trade(0.52, 10, Side.BUY, seconds_ago=25),
        _trade(0.51, 10, Side.SELL, seconds_ago=20),
        _trade(0.51, 10, Side.BUY, seconds_ago=15),
        _trade(0.50, 10, Side.SELL, seconds_ago=5),
    ]
    signal = strategy.build_signal("m1", book, trades)
    assert signal is not None
    assert signal.reason == REASON_DOWNTREND_EXIT
    assert signal.bid_price is None
    assert signal.ask_price is not None


def test_calm_market_ask_floors_at_break_even(settings, book):
    inventory = InventoryManager(settings)
    position = inventory.get_position("m1")
    position.yes_size = 10
    position.avg_yes_price = 0.60
    strategy = MarketMakingStrategy(settings, inventory)
    signal = strategy.build_signal("m1", book, [])
    assert signal is not None
    # Entry at 0.60: the resting ask must not lock in a loss in a calm market.
    assert signal.ask_price >= 0.60 + settings.min_exit_edge_ticks * settings.min_tick


def test_inventory_pressure_drops_break_even_floor(settings, book):
    inventory = InventoryManager(settings)
    position = inventory.get_position("m1")
    # 45 of max 50: inventory pressure outranks holding out for break-even.
    position.yes_size = 45
    position.avg_yes_price = 0.60
    strategy = MarketMakingStrategy(settings, inventory)
    signal = strategy.build_signal("m1", book, [])
    assert signal is not None
    assert signal.ask_price == book.best_ask
