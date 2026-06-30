import asyncio
from datetime import UTC, datetime, timedelta

from polymarket_mm_bot.backtester import BacktestEngine
from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.execution import PaperExecutionEngine
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import BookLevel, Market, OrderBook
from polymarket_mm_bot.risk import RiskEngine
from polymarket_mm_bot.strategy import MarketMakingStrategy


async def main() -> None:
    settings = Settings()
    inventory = InventoryManager(settings)
    risk = RiskEngine(settings, inventory)
    execution = PaperExecutionEngine(settings, inventory, risk)
    strategy = MarketMakingStrategy(settings, inventory)
    market = Market(
        condition_id="demo",
        question="Demo market",
        volume=50_000,
        liquidity=10_000,
        category="crypto",
        end_date=datetime.now(UTC) + timedelta(days=7),
    )
    books = [
        OrderBook(
            market_id="demo",
            bids=[BookLevel(price=0.49, size=500)],
            asks=[BookLevel(price=0.52, size=500)],
        )
        for _ in range(10)
    ]
    result = await BacktestEngine(strategy, execution, risk).run([market], {"demo": books}, {"demo": []})
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
