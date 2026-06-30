from __future__ import annotations

import asyncio

import structlog

from polymarket_mm_bot.config import get_settings
from polymarket_mm_bot.dashboard.state import state
from polymarket_mm_bot.data import PolymarketDataClient
from polymarket_mm_bot.execution import PaperExecutionEngine
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.logging import configure_logging
from polymarket_mm_bot.market_scanner import MarketScanner
from polymarket_mm_bot.models import Side
from polymarket_mm_bot.risk import RiskEngine
from polymarket_mm_bot.strategy import MarketMakingStrategy

logger = structlog.get_logger()


async def run_once() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    inventory = InventoryManager(settings)
    risk = RiskEngine(settings, inventory)
    execution = PaperExecutionEngine(settings, inventory, risk)
    strategy = MarketMakingStrategy(settings, inventory)
    scanner = MarketScanner(settings)
    data = PolymarketDataClient(settings)
    state.bot_status = "starting"
    try:
        markets = await data.fetch_active_markets()
        state.active_markets = markets
        books = {}
        trades = {}
        for market in markets[:50]:
            token_id = market.yes_token_id
            if not token_id:
                continue
            try:
                books[market.condition_id] = await data.fetch_order_book(token_id, market.condition_id)
                trades[market.condition_id] = await data.fetch_recent_trades(market.condition_id)
            except Exception as exc:
                risk.record_api_error()
                logger.warning("api_error", market_id=market.condition_id, error=str(exc))

        selected = scanner.select_markets(markets, books, trades)
        state.selected_markets = selected
        state.bot_status = "paper_trading"
        for market in selected:
            book = books.get(market.condition_id)
            if not book:
                continue
            decision = risk.check_market(market, book)
            if not decision.allowed:
                await execution.cancel_all_for_market(market.condition_id)
                state.risk_events.append({"market_id": market.condition_id, "code": decision.code})
                continue
            signal = strategy.build_signal(market.condition_id, book, trades.get(market.condition_id, []))
            if signal and signal.bid_price and signal.ask_price:
                await execution.create_order(market.condition_id, Side.BUY, signal.bid_price, signal.size, market.yes_token_id)
                await execution.create_order(market.condition_id, Side.SELL, signal.ask_price, signal.size, market.yes_token_id)
                logger.info("strategy_signal", **signal.model_dump())
            await execution.simulate_fills(book)
        await execution.cancel_stale_orders()
        state.orders = list(execution.orders.values())
        state.positions = list(inventory.positions.values())
        state.total_pnl = sum(position.realized_pnl for position in inventory.positions.values())
        state.daily_pnl = state.total_pnl
        state.strategy_status = {market.condition_id: "running" for market in selected}
    finally:
        await data.close()


async def main() -> None:
    while True:
        await run_once()
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
