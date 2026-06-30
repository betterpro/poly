from polymarket_mm_bot.execution import PaperExecutionEngine
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.market_scanner import MarketScanner
from polymarket_mm_bot.models import Side
from polymarket_mm_bot.risk import RiskEngine
from polymarket_mm_bot.strategy import MarketMakingStrategy


async def test_scanner_strategy_execution_flow(settings, market, book):
    inventory = InventoryManager(settings)
    risk = RiskEngine(settings, inventory)
    selected = MarketScanner(settings).select_markets([market], {"m1": book}, {"m1": []})
    assert selected == [market]
    signal = MarketMakingStrategy(settings, inventory).build_signal("m1", book, [])
    assert signal is not None
    execution = PaperExecutionEngine(settings, inventory, risk)
    order = await execution.create_order("m1", Side.BUY, signal.bid_price, signal.size, "yes-token")
    assert order.status == "open"
