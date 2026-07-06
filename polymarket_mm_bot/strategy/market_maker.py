from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import OrderBook, Side, StrategySignal, Trade
from polymarket_mm_bot.utils import clamp, round_to_tick

REASON_PASSIVE = "passive_spread_capture"
REASON_TOXIC_WIDEN = "toxic_flow_widen"
REASON_TOXIC_PULL = "toxic_flow_pull"


class FlowToxicity(BaseModel):
    """Snapshot of how 'informed' recent taker flow looks for one market."""

    imbalance: float = 0.0  # 0..1 fraction of volume on the dominant side
    momentum_ticks: float = 0.0  # signed price drift across the window, in ticks
    trade_count: int = 0
    level: str = "clear"  # clear | widen | pull


class MarketMakingStrategy:
    def __init__(self, settings: Settings, inventory: InventoryManager):
        self.settings = settings
        self.inventory = inventory

    def _recent_token_trades(
        self,
        order_book: OrderBook,
        trades: list[Trade] | None,
        now: datetime | None = None,
    ) -> list[Trade]:
        if not trades:
            return []
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(seconds=self.settings.toxicity_window_seconds)
        recent = []
        for trade in trades:
            timestamp = trade.timestamp
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            if timestamp < cutoff or trade.size <= 0:
                continue
            if trade.token_id and order_book.token_id and trade.token_id != order_book.token_id:
                continue
            recent.append(trade)
        recent.sort(key=lambda trade: trade.timestamp)
        return recent

    def estimate_fair_price(self, order_book: OrderBook, trades: list[Trade] | None = None) -> float | None:
        if order_book.best_bid is None or order_book.best_ask is None:
            return None
        midpoint = (order_book.best_bid + order_book.best_ask) / 2
        total_depth = order_book.bid_depth + order_book.ask_depth
        imbalance = 0.5 if total_depth <= 0 else order_book.bid_depth / total_depth
        imbalance_adjustment = (imbalance - 0.5) * self.settings.min_tick
        trade_adjustment = 0.0
        recent = self._recent_token_trades(order_book, trades)[-10:]
        if recent:
            raw_adjustment = (sum(trade.price for trade in recent) / len(recent) - midpoint) * 0.25
            trade_adjustment = clamp(raw_adjustment, -self.settings.min_tick, self.settings.min_tick)
        return clamp(midpoint + imbalance_adjustment + trade_adjustment, 0.01, 0.99)

    def assess_flow_toxicity(
        self,
        order_book: OrderBook,
        trades: list[Trade] | None,
        now: datetime | None = None,
    ) -> FlowToxicity:
        """Detect adverse selection: one-sided taker flow or fast price drift.

        When someone with information (breaking news, a live game event) is
        sweeping one side of the book, a passive market maker is the exit
        liquidity. We measure two signals over a short window:
        - volume imbalance between buyer- and seller-initiated trades
        - net price drift across the window, measured in ticks
        """
        if not trades:
            return FlowToxicity()
        now = now or datetime.now(UTC)
        recent_trades = self._recent_token_trades(order_book, trades, now)
        recent = [(trade.timestamp if trade.timestamp.tzinfo else trade.timestamp.replace(tzinfo=UTC), trade) for trade in recent_trades]
        if len(recent) < self.settings.toxicity_min_trades:
            return FlowToxicity(trade_count=len(recent))
        recent.sort(key=lambda item: item[0])

        midpoint = None
        if order_book.best_bid is not None and order_book.best_ask is not None:
            midpoint = (order_book.best_bid + order_book.best_ask) / 2

        buy_volume = 0.0
        sell_volume = 0.0
        for _, trade in recent:
            if trade.side is not None:
                is_buy = trade.side == Side.BUY
            elif midpoint is not None:
                # Tick rule fallback: trades at/above mid are buyer-initiated.
                is_buy = trade.price >= midpoint
            else:
                continue
            if is_buy:
                buy_volume += trade.size
            else:
                sell_volume += trade.size

        total_volume = buy_volume + sell_volume
        imbalance = abs(buy_volume - sell_volume) / total_volume if total_volume > 0 else 0.0
        momentum_ticks = (recent[-1][1].price - recent[0][1].price) / self.settings.min_tick

        level = "clear"
        if imbalance >= self.settings.toxicity_pull_threshold or abs(momentum_ticks) >= self.settings.toxicity_momentum_pull_ticks:
            level = "pull"
        elif imbalance >= self.settings.toxicity_widen_threshold:
            level = "widen"
        return FlowToxicity(
            imbalance=imbalance,
            momentum_ticks=momentum_ticks,
            trade_count=len(recent),
            level=level,
        )

    def build_signal(self, market_id: str, order_book: OrderBook, trades: list[Trade] | None = None) -> StrategySignal | None:
        if order_book.best_bid is None or order_book.best_ask is None:
            return None
        if order_book.spread is None or order_book.spread <= 0:
            return None
        # Sub-tick books (longshots under 1 cent, or favorites above 99) can't
        # be quoted: the 0.01..0.99 price clamp would cross the real ask/bid
        # and turn our "passive" quote into an instant taker fill.
        if order_book.best_ask <= self.settings.min_tick or order_book.best_bid >= 1 - self.settings.min_tick:
            return None
        if order_book.bid_depth + order_book.ask_depth < self.settings.min_liquidity:
            return None
        fair_price = self.estimate_fair_price(order_book, trades)
        if fair_price is None:
            return None

        toxicity = self.assess_flow_toxicity(order_book, trades)
        if toxicity.level == "pull":
            return StrategySignal(
                market_id=market_id,
                fair_price=round_to_tick(fair_price, self.settings.min_tick),
                bid_price=None,
                ask_price=None,
                size=0.0,
                reason=REASON_TOXIC_PULL,
            )

        target_spread = max(self.settings.target_spread, self.settings.min_spread)
        size = self.settings.order_size
        reason = REASON_PASSIVE
        if toxicity.level == "widen":
            target_spread *= self.settings.toxicity_spread_multiplier
            size = max(size * self.settings.toxicity_size_multiplier, 1.0)
            reason = REASON_TOXIC_WIDEN

        skew = self.inventory.inventory_skew(market_id)
        bid = fair_price - target_spread / 2 - max(skew, 0) * self.settings.min_tick
        ask = fair_price + target_spread / 2 - skew * self.settings.min_tick

        # Stay passive: joining the current best bid/ask is acceptable, but
        # crossing the spread turns the paper bot into a taker and distorts PnL.
        bid = min(bid, order_book.best_bid)
        ask = max(ask, order_book.best_ask)
        bid = round_to_tick(clamp(bid, 0.01, 0.99), self.settings.min_tick)
        ask = round_to_tick(clamp(ask, 0.01, 0.99), self.settings.min_tick)

        if bid >= ask:
            return None

        return StrategySignal(
            market_id=market_id,
            fair_price=round_to_tick(fair_price, self.settings.min_tick),
            bid_price=bid,
            ask_price=ask,
            size=size,
            reason=reason,
        )
