from polymarket_mm_bot.execution import PaperExecutionEngine
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import Side
from polymarket_mm_bot.risk import RiskEngine


async def test_paper_fill_updates_order_and_position(settings, book):
    inventory = InventoryManager(settings)
    risk = RiskEngine(settings, inventory)
    execution = PaperExecutionEngine(settings, inventory, risk)
    order = await execution.create_order("m1", Side.BUY, 0.53, 10, "yes-token")
    fills = await execution.simulate_fills(book)
    assert fills[0].client_order_id == order.client_order_id
    assert inventory.get_position("m1").yes_size == 10
