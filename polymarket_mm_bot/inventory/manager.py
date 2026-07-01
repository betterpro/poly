from collections import defaultdict

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.models import BotOrder, Outcome, Position, Side


class InventoryManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.positions: dict[str, Position] = defaultdict(lambda: Position(market_id=""))

    def get_position(self, market_id: str) -> Position:
        position = self.positions[market_id]
        if not position.market_id:
            position.market_id = market_id
        return position

    def can_quote_side(self, market_id: str, side: Side, outcome: Outcome = Outcome.YES) -> bool:
        position = self.get_position(market_id)
        projected = abs(position.net_yes)
        if side == Side.BUY:
            projected += self.settings.order_size
        else:
            projected = max(projected - self.settings.order_size, 0)
        return projected <= self.settings.max_position_per_market

    def inventory_skew(self, market_id: str) -> float:
        position = self.get_position(market_id)
        limit = max(self.settings.max_position_per_market, 1)
        return max(-1.0, min(1.0, position.net_yes / limit))

    def apply_fill(self, order: BotOrder, fill_size: float, fill_price: float) -> Position:
        position = self.get_position(order.market_id)
        if order.outcome == Outcome.NO:
            if order.side == Side.BUY:
                position.no_size, position.avg_no_price = self._add_lot(
                    position.no_size, position.avg_no_price, fill_size, fill_price
                )
            else:
                position.no_size -= fill_size
                position.realized_pnl += (fill_price - position.avg_no_price) * fill_size
        else:
            if order.side == Side.BUY:
                position.yes_size, position.avg_yes_price = self._add_lot(
                    position.yes_size, position.avg_yes_price, fill_size, fill_price
                )
            else:
                position.yes_size -= fill_size
                position.realized_pnl += (fill_price - position.avg_yes_price) * fill_size
        return position

    def unrealized_pnl(self, market_id: str, yes_mark_price: float) -> float:
        position = self.get_position(market_id)
        unrealized = 0.0
        if position.yes_size > 0:
            unrealized += position.yes_size * (yes_mark_price - position.avg_yes_price)
        if position.no_size > 0:
            no_mark_price = 1.0 - yes_mark_price
            unrealized += position.no_size * (no_mark_price - position.avg_no_price)
        return unrealized

    def portfolio_pnl(self, mark_prices: dict[str, float]) -> tuple[float, float, float]:
        realized = sum(position.realized_pnl for position in self.positions.values())
        unrealized = sum(
            self.unrealized_pnl(market_id, mark_price)
            for market_id, mark_price in mark_prices.items()
            if self._position_is_open(self.positions[market_id])
        )
        return realized, unrealized, realized + unrealized

    @staticmethod
    def _position_is_open(position: Position) -> bool:
        return position.yes_size > 0 or position.no_size > 0 or position.realized_pnl != 0

    def total_exposure(self) -> float:
        return sum(position.gross_exposure for position in self.positions.values())

    @staticmethod
    def _add_lot(size: float, avg_price: float, fill_size: float, fill_price: float) -> tuple[float, float]:
        new_size = size + fill_size
        if new_size <= 0:
            return 0, 0
        return new_size, ((size * avg_price) + (fill_size * fill_price)) / new_size
