from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import OrderBook, StrategySignal, Trade
from polymarket_mm_bot.utils import clamp, round_to_tick


class MarketMakingStrategy:
    def __init__(self, settings: Settings, inventory: InventoryManager):
        self.settings = settings
        self.inventory = inventory

    def estimate_fair_price(self, order_book: OrderBook, trades: list[Trade] | None = None) -> float | None:
        if order_book.best_bid is None or order_book.best_ask is None:
            return None
        midpoint = (order_book.best_bid + order_book.best_ask) / 2
        total_depth = order_book.bid_depth + order_book.ask_depth
        imbalance = 0.5 if total_depth <= 0 else order_book.bid_depth / total_depth
        imbalance_adjustment = (imbalance - 0.5) * self.settings.min_tick
        trade_adjustment = 0.0
        if trades:
            recent = trades[-10:]
            trade_adjustment = (sum(trade.price for trade in recent) / len(recent) - midpoint) * 0.25
        return clamp(midpoint + imbalance_adjustment + trade_adjustment, 0.01, 0.99)

    def build_signal(self, market_id: str, order_book: OrderBook, trades: list[Trade] | None = None) -> StrategySignal | None:
        if order_book.best_bid is None or order_book.best_ask is None:
            return None
        if order_book.spread is None or order_book.spread <= 0:
            return None
        if order_book.bid_depth + order_book.ask_depth < self.settings.min_liquidity:
            return None
        fair_price = self.estimate_fair_price(order_book, trades)
        if fair_price is None:
            return None

        skew = self.inventory.inventory_skew(market_id)
        target_spread = max(self.settings.target_spread, self.settings.min_spread)
        bid = fair_price - target_spread / 2 - max(skew, 0) * self.settings.min_tick
        ask = fair_price + target_spread / 2 - min(skew, 0) * self.settings.min_tick

        bid = min(bid, (order_book.best_bid or bid) + self.settings.min_tick)
        ask = max(ask, (order_book.best_ask or ask) - self.settings.min_tick)
        bid = round_to_tick(clamp(bid, 0.01, 0.99), self.settings.min_tick)
        ask = round_to_tick(clamp(ask, 0.01, 0.99), self.settings.min_tick)

        if bid >= ask:
            return None

        return StrategySignal(
            market_id=market_id,
            fair_price=round_to_tick(fair_price, self.settings.min_tick),
            bid_price=bid,
            ask_price=ask,
            size=self.settings.order_size,
            reason="passive_spread_capture",
        )
