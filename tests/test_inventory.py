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
