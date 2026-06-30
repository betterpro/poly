from dataclasses import dataclass, field

import numpy as np

from polymarket_mm_bot.execution import PaperExecutionEngine
from polymarket_mm_bot.models import Market, OrderBook, Side, Trade
from polymarket_mm_bot.risk import RiskEngine
from polymarket_mm_bot.strategy import MarketMakingStrategy


@dataclass
class BacktestResult:
    total_pnl: float
    win_rate: float
    max_drawdown: float
    sharpe_like: float
    fill_rate: float
    average_spread_captured: float
    average_holding_time: float
    pnl_by_market: dict[str, float] = field(default_factory=dict)
    pnl_by_category: dict[str, float] = field(default_factory=dict)


class BacktestEngine:
    def __init__(self, strategy: MarketMakingStrategy, execution: PaperExecutionEngine, risk: RiskEngine):
        self.strategy = strategy
        self.execution = execution
        self.risk = risk

    async def run(
        self,
        markets: list[Market],
        books_by_market: dict[str, list[OrderBook]],
        trades_by_market: dict[str, list[Trade]],
    ) -> BacktestResult:
        equity_curve = [0.0]
        orders_sent = 0
        fills = 0
        spread_captured: list[float] = []
        pnl_by_market: dict[str, float] = {}
        pnl_by_category: dict[str, float] = {}

        market_lookup = {market.condition_id: market for market in markets}
        for market_id, books in books_by_market.items():
            for book in books:
                signal = self.strategy.build_signal(market_id, book, trades_by_market.get(market_id, []))
                if signal and signal.bid_price and signal.ask_price:
                    await self.execution.create_order(market_id, Side.BUY, signal.bid_price, signal.size, book.token_id)
                    await self.execution.create_order(market_id, Side.SELL, signal.ask_price, signal.size, book.token_id)
                    orders_sent += 2
                filled_orders = await self.execution.simulate_fills(book)
                fills += len(filled_orders)
                if len(filled_orders) >= 2:
                    spread_captured.append(abs(filled_orders[-1].price - filled_orders[-2].price))
                position = self.execution.inventory.get_position(market_id)
                pnl_by_market[market_id] = position.realized_pnl
                category = market_lookup.get(market_id).category if market_lookup.get(market_id) else "unknown"
                pnl_by_category[category or "unknown"] = pnl_by_category.get(category or "unknown", 0) + position.realized_pnl
                equity_curve.append(sum(p.realized_pnl for p in self.execution.inventory.positions.values()))

        returns = np.diff(equity_curve)
        total_pnl = equity_curve[-1]
        wins = len([value for value in returns if value > 0])
        drawdown = max((max(equity_curve[: i + 1]) - value for i, value in enumerate(equity_curve)), default=0)
        sharpe_like = float(np.mean(returns) / np.std(returns)) if len(returns) > 1 and np.std(returns) > 0 else 0.0
        return BacktestResult(
            total_pnl=round(total_pnl, 4),
            win_rate=wins / len(returns) if len(returns) else 0.0,
            max_drawdown=round(drawdown, 4),
            sharpe_like=round(sharpe_like, 4),
            fill_rate=fills / orders_sent if orders_sent else 0.0,
            average_spread_captured=float(np.mean(spread_captured)) if spread_captured else 0.0,
            average_holding_time=0.0,
            pnl_by_market=pnl_by_market,
            pnl_by_category=pnl_by_category,
        )
