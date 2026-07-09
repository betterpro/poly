"""Queue-priority improvement: step inside a wide touch without giving up edge."""

from __future__ import annotations

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import BookLevel, OrderBook
from polymarket_mm_bot.strategy import MarketMakingStrategy


def _wide_book() -> OrderBook:
    # 20-cent-wide book: best bid 0.40, best ask 0.60.
    return OrderBook(
        market_id="m1",
        token_id="t",
        bids=[BookLevel(price=0.40, size=800)],
        asks=[BookLevel(price=0.60, size=800)],
    )


def _tight_book() -> OrderBook:
    # 2-cent book: too tight to step inside and keep target edge.
    return OrderBook(
        market_id="m1",
        token_id="t",
        bids=[BookLevel(price=0.49, size=800)],
        asks=[BookLevel(price=0.51, size=800)],
    )


def test_steps_inside_wide_book_and_keeps_edge():
    s = Settings(min_liquidity=100, quote_improve_ticks=1)
    signal = MarketMakingStrategy(s, InventoryManager(s)).build_signal("m1", _wide_book(), [])
    assert signal is not None
    # Improved past the touch on both sides...
    assert signal.bid_price > 0.40
    assert signal.ask_price < 0.60
    # ...still brackets fair and keeps at least target_spread of edge.
    assert signal.bid_price < 0.50 < signal.ask_price
    assert signal.ask_price - signal.bid_price >= s.target_spread - 1e-9


def test_disabled_sits_at_touch():
    s = Settings(min_liquidity=100, quote_improve_ticks=0)
    signal = MarketMakingStrategy(s, InventoryManager(s)).build_signal("m1", _wide_book(), [])
    assert signal is not None
    assert signal.bid_price == 0.40
    assert signal.ask_price == 0.60


def test_tight_book_not_improved():
    # Stepping inside a 2c book would erase the edge, so quotes stay at the touch.
    s = Settings(min_liquidity=100, quote_improve_ticks=1)
    signal = MarketMakingStrategy(s, InventoryManager(s)).build_signal("m1", _tight_book(), [])
    assert signal is not None
    assert signal.bid_price == 0.49
    assert signal.ask_price == 0.51


def test_improvement_never_crosses_or_undercuts_min_spread():
    s = Settings(min_liquidity=100, quote_improve_ticks=5)  # aggressive
    signal = MarketMakingStrategy(s, InventoryManager(s)).build_signal("m1", _wide_book(), [])
    assert signal is not None
    assert signal.bid_price < signal.ask_price
    assert signal.ask_price - signal.bid_price >= s.min_spread - 1e-9
