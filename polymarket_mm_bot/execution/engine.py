from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Protocol

import structlog

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import BotOrder, OrderBook, OrderStatus, Outcome, Side
from polymarket_mm_bot.risk import RiskEngine

logger = structlog.get_logger()


class ExecutionEngine(Protocol):
    orders: dict[str, BotOrder]

    async def create_order(self, market_id: str, side: Side, price: float, size: float, token_id: str | None = None) -> BotOrder:
        ...

    async def cancel_order(self, client_order_id: str) -> None:
        ...

    async def cancel_all_for_market(self, market_id: str) -> None:
        ...


class PaperExecutionEngine:
    def __init__(self, settings: Settings, inventory: InventoryManager, risk: RiskEngine):
        self.settings = settings
        self.inventory = inventory
        self.risk = risk
        self.orders: dict[str, BotOrder] = {}

    async def create_order(
        self,
        market_id: str,
        side: Side,
        price: float,
        size: float,
        token_id: str | None = None,
        outcome: Outcome = Outcome.YES,
    ) -> BotOrder:
        order = BotOrder(
            client_order_id=f"paper-{uuid.uuid4()}",
            market_id=market_id,
            token_id=token_id,
            side=side,
            outcome=outcome,
            price=price,
            size=size,
        )
        decision = self.risk.check_order(order, list(self.orders.values()))
        if not decision.allowed:
            order.status = OrderStatus.REJECTED
            logger.warning("order_rejected", reason=decision.code, market_id=market_id)
            return order
        self.orders[order.client_order_id] = order
        logger.info("order_created", **order.model_dump(mode="json"))
        return order

    async def cancel_order(self, client_order_id: str) -> None:
        order = self.orders.get(client_order_id)
        if not order or order.status not in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
            return
        order.status = OrderStatus.CANCELED
        order.updated_at = datetime.now(UTC)
        logger.info("order_canceled", client_order_id=client_order_id, market_id=order.market_id)

    async def cancel_all_for_market(self, market_id: str) -> None:
        for order in list(self.orders.values()):
            if order.market_id == market_id:
                await self.cancel_order(order.client_order_id)

    async def cancel_stale_orders(self) -> None:
        now = datetime.now(UTC)
        for order in list(self.orders.values()):
            if order.status == OrderStatus.OPEN and (now - order.created_at).total_seconds() > self.settings.stale_order_seconds:
                await self.cancel_order(order.client_order_id)

    async def simulate_fills(self, order_book: OrderBook) -> list[BotOrder]:
        filled: list[BotOrder] = []
        for order in self.orders.values():
            if order.market_id != order_book.market_id or order.status not in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
                continue
            crossed = (order.side == Side.BUY and order_book.best_ask is not None and order.price >= order_book.best_ask) or (
                order.side == Side.SELL and order_book.best_bid is not None and order.price <= order_book.best_bid
            )
            passive_trade_through = (
                order.side == Side.BUY
                and order_book.best_bid is not None
                and order.price >= order_book.best_bid
                and order_book.bid_depth > order.size * 3
            ) or (
                order.side == Side.SELL
                and order_book.best_ask is not None
                and order.price <= order_book.best_ask
                and order_book.ask_depth > order.size * 3
            )
            if crossed or passive_trade_through:
                fill_size = order.remaining_size
                order.filled_size += fill_size
                order.status = OrderStatus.FILLED
                order.updated_at = datetime.now(UTC)
                self.inventory.apply_fill(order, fill_size, order.price)
                filled.append(order)
                logger.info("fill_received", client_order_id=order.client_order_id, fill_size=fill_size, price=order.price)
        return filled


class LiveExecutionEngine:
    def __init__(self, settings: Settings):
        if settings.paper_trading or not settings.live_trading_confirmed:
            raise ValueError("LiveExecutionEngine cannot start while paper trading is enabled.")
        if not settings.polymarket_private_key:
            raise ValueError("Missing private key for live trading.")
        self.settings = settings
        self.orders: dict[str, BotOrder] = {}

    async def create_order(self, *args, **kwargs) -> BotOrder:  # pragma: no cover - guarded adapter stub
        raise NotImplementedError(
            "Live order placement must be implemented with py_clob_client_v2 and manually reviewed before enabling."
        )

    async def cancel_order(self, client_order_id: str) -> None:  # pragma: no cover
        raise NotImplementedError

    async def cancel_all_for_market(self, market_id: str) -> None:  # pragma: no cover
        raise NotImplementedError
