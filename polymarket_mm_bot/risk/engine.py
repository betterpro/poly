from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import BotOrder, Market, OrderBook, OrderStatus, Outcome, Side

logger = structlog.get_logger()


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    code: str = "ok"
    message: str = "allowed"


class RiskEngine:
    def __init__(self, settings: Settings, inventory: InventoryManager):
        self.settings = settings
        self.inventory = inventory
        self.api_errors = 0
        self.market_failures: dict[str, int] = {}
        self.paused_markets: set[str] = set()
        self.daily_pnl = 0.0

    def check_market(self, market: Market, book: OrderBook | None = None) -> RiskDecision:
        if market.condition_id in self.paused_markets:
            return self._deny("market_paused_by_risk", market.condition_id)
        if not market.active or market.closed or market.paused:
            return self._deny("market_not_tradeable", market.condition_id)
        if market.end_date:
            hours = (market.end_date - datetime.now(UTC)).total_seconds() / 3600
            if hours < self.settings.min_time_to_resolution_hours and not self.settings.allow_near_resolution:
                return self._deny("near_resolution", market.condition_id)
        if book and (datetime.now(UTC) - book.updated_at).total_seconds() > self.settings.stale_data_seconds:
            return self._deny("stale_market_data", market.condition_id)
        return RiskDecision(True)

    def check_order(self, order: BotOrder, open_orders: list[BotOrder]) -> RiskDecision:
        if order.size > self.settings.max_order_size:
            return self._deny("max_order_size", order.market_id)
        if len([o for o in open_orders if o.status == OrderStatus.OPEN]) >= self.settings.max_open_orders:
            return self._deny("max_open_orders", order.market_id)
        projected_exposure = self._project_total_exposure(order)
        if projected_exposure > self.settings.max_total_exposure:
            return self._deny("max_total_exposure", order.market_id)
        projected_market_exposure = self._project_market_exposure(order)
        if projected_market_exposure is None:
            return self._deny("insufficient_inventory", order.market_id)
        if projected_market_exposure > self.settings.max_position_per_market:
            return self._deny("max_position_per_market", order.market_id)
        if self.daily_pnl <= -abs(self.settings.max_daily_loss):
            return self._deny("max_daily_loss", order.market_id)
        return RiskDecision(True)

    def record_order_failure(self, market_id: str) -> RiskDecision:
        failures = self.market_failures.get(market_id, 0) + 1
        self.market_failures[market_id] = failures
        if failures >= self.settings.max_order_failures_per_market:
            self.paused_markets.add(market_id)
            return self._deny("consecutive_order_failures", market_id)
        return RiskDecision(True)

    def record_api_error(self) -> RiskDecision:
        self.api_errors += 1
        if self.api_errors >= self.settings.max_api_errors:
            return self._deny("api_error_threshold", None)
        return RiskDecision(True)

    def update_daily_pnl(self, pnl: float) -> RiskDecision:
        self.daily_pnl = pnl
        if pnl <= -abs(self.settings.max_daily_loss):
            return self._deny("max_daily_loss", None)
        return RiskDecision(True)

    def _deny(self, code: str, market_id: str | None) -> RiskDecision:
        logger.warning("risk_event", code=code, market_id=market_id)
        return RiskDecision(False, code, f"Risk blocked trading: {code}")

    def _project_market_exposure(self, order: BotOrder) -> float | None:
        position = self.inventory.get_position(order.market_id)
        yes_size = position.yes_size
        no_size = position.no_size
        if order.outcome == Outcome.YES:
            if order.side == Side.BUY:
                yes_size += order.size
            elif order.size > yes_size:
                return None
            else:
                yes_size -= order.size
        else:
            if order.side == Side.BUY:
                no_size += order.size
            elif order.size > no_size:
                return None
            else:
                no_size -= order.size
        return max(yes_size, no_size, abs(yes_size - no_size))

    def _project_total_exposure(self, order: BotOrder) -> float:
        total = 0.0
        for market_id, position in self.inventory.positions.items():
            market_exposure = position.gross_exposure
            if market_id == order.market_id:
                if order.outcome == Outcome.YES:
                    if order.side == Side.BUY:
                        market_exposure += order.size * order.price
                    else:
                        market_exposure -= min(order.size, position.yes_size) * position.avg_yes_price
                else:
                    if order.side == Side.BUY:
                        market_exposure += order.size * order.price
                    else:
                        market_exposure -= min(order.size, position.no_size) * position.avg_no_price
            total += max(0.0, market_exposure)
        if order.market_id not in self.inventory.positions and order.side == Side.BUY:
            total += order.size * order.price
        return total
