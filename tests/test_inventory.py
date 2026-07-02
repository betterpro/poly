from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import BotOrder, Side


def test_inventory_updates_position_and_pnl(settings):
    inventory = InventoryManager(settings)
    buy = BotOrder(client_order_id="1", market_id="m1", side=Side.BUY, price=0.5, size=10)
    sell = BotOrder(client_order_id="2", market_id="m1", side=Side.SELL, price=0.55, size=10)
    inventory.apply_fill(buy, 10, 0.5)
    position = inventory.apply_fill(sell, 10, 0.55)
    assert position.yes_size == 0
    assert round(position.realized_pnl, 2) == 0.5


def test_inventory_unrealized_pnl(settings):
    inventory = InventoryManager(settings)
    buy = BotOrder(client_order_id="1", market_id="m1", side=Side.BUY, price=0.4, size=10)
    inventory.apply_fill(buy, 10, 0.4)
    assert round(inventory.unrealized_pnl("m1", 0.45), 2) == 0.5
    realized, unrealized, total = inventory.portfolio_pnl({"m1": 0.45})
    assert realized == 0.0
    assert round(unrealized, 2) == 0.5
    assert round(total, 2) == 0.5


def test_portfolio_pnl_ignores_mark_prices_without_positions(settings):
    inventory = InventoryManager(settings)
    realized, unrealized, total = inventory.portfolio_pnl(
        {"selected-no-book": 0.55, "another-ghost": 0.60}
    )
    assert realized == 0.0
    assert unrealized == 0.0
    assert total == 0.0
    assert list(inventory.positions.keys()) == []
