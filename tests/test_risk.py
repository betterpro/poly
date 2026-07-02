from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import BotOrder, Side
from polymarket_mm_bot.risk import RiskEngine


def test_risk_blocks_large_order(settings):
    inventory = InventoryManager(settings)
    risk = RiskEngine(settings, inventory)
    order = BotOrder(client_order_id="1", market_id="m1", side=Side.BUY, price=0.5, size=999)
    decision = risk.check_order(order, [])
    assert decision.allowed is False
    assert decision.code == "max_order_size"


def test_risk_pauses_after_failures(settings):
    risk = RiskEngine(settings, InventoryManager(settings))
    decision = None
    for _ in range(settings.max_order_failures_per_market):
        decision = risk.record_order_failure("m1")
    assert decision is not None
    assert decision.allowed is False
    assert "m1" in risk.paused_markets


def test_risk_allows_sell_that_reduces_exposure_at_limit(settings):
    settings.max_total_exposure = 5
    inventory = InventoryManager(settings)
    position = inventory.get_position("m1")
    position.yes_size = 10
    position.avg_yes_price = 0.5
    risk = RiskEngine(settings, inventory)
    order = BotOrder(client_order_id="1", market_id="m1", side=Side.SELL, price=0.55, size=5)
    decision = risk.check_order(order, [])
    assert decision.allowed is True
