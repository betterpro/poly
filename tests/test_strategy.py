from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.strategy import MarketMakingStrategy


def test_strategy_builds_non_crossing_quotes(settings, book):
    strategy = MarketMakingStrategy(settings, InventoryManager(settings))
    signal = strategy.build_signal("m1", book, [])
    assert signal is not None
    assert signal.bid_price < signal.ask_price
    assert 0.01 <= signal.bid_price <= 0.99
    assert 0.01 <= signal.ask_price <= 0.99
