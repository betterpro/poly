from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

import structlog
from sqlalchemy.orm import Session, sessionmaker

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.database.runtime_state import save_fill, save_order, save_position
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import BotOrder, OrderBook, OrderStatus, Outcome, Side, Trade
from polymarket_mm_bot.risk import RiskEngine

logger = structlog.get_logger()

if TYPE_CHECKING:
    from polymarket_mm_bot.execution.live_client import ClobGateway

# LiveExecutionEngine now places and reconciles real orders through the CLOB
# gateway. Live trading still requires PAPER_TRADING=false, LIVE_TRADING_CONFIRMED,
# wallet credentials, the TOTP switch, and a passing preflight before it can arm.
LIVE_EXECUTION_IMPLEMENTED = True

# Keep at most this many recent fills in memory for the dashboard trade feed.
_MAX_RECENT_FILLS = 200


def record_fill(store: list[dict], order: BotOrder, size: float, price: float) -> None:
    """Append a fill event to a rolling in-memory feed (newest last)."""
    store.append(
        {
            "order_id": order.client_order_id,
            "market_id": order.market_id,
            "side": order.side.value,
            "outcome": order.outcome.value,
            "price": round(price, 6),
            "size": round(size, 6),
            "value": round(size * price, 6),
            "status": order.status.value,
            "at": datetime.now(UTC).isoformat(),
        }
    )
    if len(store) > _MAX_RECENT_FILLS:
        del store[: len(store) - _MAX_RECENT_FILLS]


def _safe_persist_order(session_factory: sessionmaker[Session] | None, order: BotOrder) -> None:
    if session_factory is None:
        return
    try:
        with session_factory() as session:
            save_order(session, order)
    except Exception as exc:
        logger.warning("order_persist_failed", client_order_id=order.client_order_id, error=str(exc))


def _safe_persist_fill(
    session_factory: sessionmaker[Session] | None,
    order: BotOrder,
    fill_size: float,
    fill_price: float,
) -> None:
    if session_factory is None:
        return
    try:
        with session_factory() as session:
            save_fill(session, order, fill_size, fill_price)
    except Exception as exc:
        logger.warning("fill_persist_failed", client_order_id=order.client_order_id, error=str(exc))


def _safe_persist_position(
    session_factory: sessionmaker[Session] | None,
    inventory: InventoryManager,
    market_id: str,
) -> None:
    if session_factory is None:
        return
    try:
        with session_factory() as session:
            save_position(session, inventory.get_position(market_id))
    except Exception as exc:
        logger.warning("position_persist_failed", market_id=market_id, error=str(exc))


class ExecutionEngine(Protocol):
    orders: dict[str, BotOrder]

    async def create_order(self, market_id: str, side: Side, price: float, size: float, token_id: str | None = None) -> BotOrder:
        ...

    async def cancel_order(self, client_order_id: str) -> None:
        ...

    async def cancel_all_for_market(self, market_id: str) -> None:
        ...


class PaperExecutionEngine:
    def __init__(
        self,
        settings: Settings,
        inventory: InventoryManager,
        risk: RiskEngine,
        *,
        orders: dict[str, BotOrder] | None = None,
        session_factory: sessionmaker[Session] | None = None,
    ):
        self.settings = settings
        self.inventory = inventory
        self.risk = risk
        self.orders: dict[str, BotOrder] = orders or {}
        self.session_factory = session_factory
        self.recent_fills: list[dict] = []
        # Per-order timestamp watermark so the same market prints are never
        # counted twice when simulating passive maker fills across cycles.
        self._maker_cursor: dict[str, datetime] = {}

    def _persist_order(self, order: BotOrder) -> None:
        _safe_persist_order(self.session_factory, order)

    def _persist_position(self, market_id: str) -> None:
        _safe_persist_position(self.session_factory, self.inventory, market_id)

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
            self._persist_order(order)
            return order
        self.orders[order.client_order_id] = order
        self._persist_order(order)
        logger.info("order_created", **order.model_dump(mode="json"))
        return order

    async def cancel_order(self, client_order_id: str) -> None:
        order = self.orders.get(client_order_id)
        if not order or order.status not in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
            return
        order.status = OrderStatus.CANCELED
        order.updated_at = datetime.now(UTC)
        self._maker_cursor.pop(client_order_id, None)
        self._persist_order(order)
        logger.info("order_canceled", client_order_id=client_order_id, market_id=order.market_id)

    async def cancel_all_for_market(self, market_id: str) -> None:
        for order in list(self.orders.values()):
            if order.market_id == market_id:
                await self.cancel_order(order.client_order_id)

    async def cancel_all_open_orders(self) -> None:
        for order in list(self.orders.values()):
            if order.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
                await self.cancel_order(order.client_order_id)

    async def cancel_stale_orders(self) -> None:
        now = datetime.now(UTC)
        for order in list(self.orders.values()):
            if order.status == OrderStatus.OPEN and (now - order.created_at).total_seconds() > self.settings.stale_order_seconds:
                await self.cancel_order(order.client_order_id)

    async def simulate_fills(self, order_book: OrderBook, trades: list[Trade] | None = None) -> list[BotOrder]:
        filled: list[BotOrder] = []
        for order in self.orders.values():
            if order.market_id != order_book.market_id or order.status not in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
                continue
            volume_cap: float | None = None
            if not self._order_crosses_book(order, order_book):
                # Passive (maker) fill: the quote rests in the book, so it only
                # fills when real market prints trade at or through its price.
                volume_cap = self._maker_fill_volume(order, trades)
                if volume_cap <= 0:
                    continue
            fill_size = min(order.remaining_size, self._allowed_fill_size(order))
            if volume_cap is not None:
                fill_size = min(fill_size, volume_cap)
            if fill_size <= 0:
                continue
            order.filled_size += fill_size
            order.status = OrderStatus.FILLED if order.remaining_size <= 0 else OrderStatus.PARTIALLY_FILLED
            order.updated_at = datetime.now(UTC)
            self.inventory.apply_fill(order, fill_size, order.price)
            self._persist_order(order)
            self._persist_position(order.market_id)
            _safe_persist_fill(self.session_factory, order, fill_size, order.price)
            record_fill(self.recent_fills, order, fill_size, order.price)
            filled.append(order)
            logger.info("fill_received", client_order_id=order.client_order_id, fill_size=fill_size, price=order.price)
        return filled

    def _order_crosses_book(self, order: BotOrder, order_book: OrderBook) -> bool:
        if order.side == Side.BUY:
            return order_book.best_ask is not None and order.price >= order_book.best_ask
        return order_book.best_bid is not None and order.price <= order_book.best_bid

    def _maker_fill_volume(self, order: BotOrder, trades: list[Trade] | None) -> float:
        """Volume of real market prints that would have hit our resting quote.

        A resting BUY fills when the market trades at or below our bid; a
        resting SELL fills when it trades at or above our ask. A per-order
        watermark ensures each print is only counted once even though the same
        recent-trades feed is seen on multiple cycles.
        """
        if not trades:
            return 0.0
        cutoff = self._maker_cursor.get(order.client_order_id, order.created_at)
        volume = 0.0
        latest = cutoff
        for trade in trades:
            timestamp = trade.timestamp
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            if timestamp <= cutoff:
                continue
            latest = max(latest, timestamp)
            # Prints on the other outcome token are quoted in that token's
            # price space (NO = 1 - YES) and must not fill a YES order.
            if trade.token_id and order.token_id and trade.token_id != order.token_id:
                continue
            if order.side == Side.BUY and trade.price <= order.price:
                # Only seller-initiated prints can hit our resting bid.
                if trade.side is None or trade.side == Side.SELL:
                    volume += trade.size
            elif order.side == Side.SELL and trade.price >= order.price:
                # Only buyer-initiated prints can lift our resting ask.
                if trade.side is None or trade.side == Side.BUY:
                    volume += trade.size
        self._maker_cursor[order.client_order_id] = latest
        return volume

    def _allowed_fill_size(self, order: BotOrder) -> float:
        position = self.inventory.get_position(order.market_id)
        if order.side == Side.BUY and order.outcome == Outcome.YES:
            room = self.settings.max_position_per_market - position.yes_size
            return max(0.0, min(order.remaining_size, room))
        if order.side == Side.SELL and order.outcome == Outcome.YES:
            return max(0.0, min(order.remaining_size, position.yes_size))
        if order.side == Side.BUY and order.outcome == Outcome.NO:
            room = self.settings.max_position_per_market - position.no_size
            return max(0.0, min(order.remaining_size, room))
        if order.side == Side.SELL and order.outcome == Outcome.NO:
            return max(0.0, min(order.remaining_size, position.no_size))
        return order.remaining_size


class LiveExecutionEngine:
    """Places and reconciles real orders on Polymarket through a ClobGateway.

    Fills are NOT simulated: they are learned by reconciling against the
    exchange's own trades/open-orders (see :meth:`sync_fills`). The gateway can be
    injected for testing; in production it is lazily built from settings.
    """

    def __init__(
        self,
        settings: Settings,
        inventory: InventoryManager,
        risk: RiskEngine,
        *,
        orders: dict[str, BotOrder] | None = None,
        session_factory: "sessionmaker[Session] | None" = None,
        gateway: "ClobGateway | None" = None,
    ):
        if settings.paper_trading or not settings.live_trading_confirmed:
            raise ValueError("LiveExecutionEngine cannot start while paper trading is enabled.")
        if not settings.polymarket_private_key:
            raise ValueError("Missing private key for live trading.")
        if not settings.polymarket_funder_address:
            raise ValueError("Missing funder address for live trading.")
        self.settings = settings
        self.inventory = inventory
        self.risk = risk
        self.orders: dict[str, BotOrder] = orders or {}
        self.session_factory = session_factory
        self.recent_fills: list[dict] = []
        self._gateway_impl = gateway
        # Track matched (size, notional) per order id so reconciliation applies only
        # incremental fills and never double-counts across restarts.
        self._matched: dict[str, tuple[float, float]] = {}
        for order_id, order in self.orders.items():
            if order.filled_size > 0:
                self._matched[order_id] = (order.filled_size, order.filled_size * order.price)

    def _gateway(self) -> "ClobGateway":
        if self._gateway_impl is None:
            from polymarket_mm_bot.execution.live_client import build_gateway

            self._gateway_impl = build_gateway(self.settings)
        return self._gateway_impl

    def preflight(self) -> None:
        """Verify the exchange is reachable and collateral/allowance are sufficient.

        Raises RuntimeError so the runtime can fall back to a safe idle state.
        """
        from polymarket_mm_bot.execution.live_client import ClobUnavailable

        try:
            gateway = self._gateway()
            balance = gateway.collateral_balance()
            allowance = gateway.collateral_allowance()
        except ClobUnavailable as exc:
            raise RuntimeError(f"Live preflight failed: {exc}") from exc
        except Exception as exc:
            raise RuntimeError(f"Live preflight failed: exchange unreachable ({exc}).") from exc
        if balance <= 0:
            raise RuntimeError("Live preflight failed: zero USDC collateral balance.")
        if allowance < self.settings.max_total_exposure:
            raise RuntimeError(
                f"Live preflight failed: USDC allowance {allowance} < max_total_exposure "
                f"{self.settings.max_total_exposure}. Approve collateral before trading live."
            )
        logger.info("live_preflight_ok", balance=balance, allowance=allowance)

    def _persist_order(self, order: BotOrder) -> None:
        _safe_persist_order(self.session_factory, order)

    def _persist_position(self, market_id: str) -> None:
        _safe_persist_position(self.session_factory, self.inventory, market_id)

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
            client_order_id=f"pending-{uuid.uuid4()}",
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
        if not token_id:
            order.status = OrderStatus.REJECTED
            logger.warning("order_rejected", reason="missing_token_id", market_id=market_id)
            return order
        try:
            placed = self._gateway().place_order(token_id, side, price, size)
        except Exception as exc:
            order.status = OrderStatus.REJECTED
            logger.error("live_order_failed", market_id=market_id, error=str(exc))
            self.risk.record_order_failure(market_id)
            return order
        # Use the exchange order id as our key so reconciliation and DB persistence
        # line up with what the exchange reports.
        order.client_order_id = placed.order_id
        self.orders[order.client_order_id] = order
        self._persist_order(order)
        logger.info(
            "live_order_placed",
            order_id=order.client_order_id,
            market_id=market_id,
            side=side.value,
            price=price,
            size=size,
        )
        return order

    async def cancel_order(self, client_order_id: str) -> None:
        order = self.orders.get(client_order_id)
        if not order or order.status not in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
            return
        try:
            self._gateway().cancel(client_order_id)
        except Exception as exc:
            logger.error("live_cancel_failed", order_id=client_order_id, error=str(exc))
            return
        order.status = OrderStatus.CANCELED
        order.updated_at = datetime.now(UTC)
        self._persist_order(order)
        logger.info("order_canceled", client_order_id=client_order_id, market_id=order.market_id)

    async def cancel_all_for_market(self, market_id: str) -> None:
        for order in list(self.orders.values()):
            if order.market_id == market_id:
                await self.cancel_order(order.client_order_id)

    async def cancel_all_open_orders(self) -> None:
        for order in list(self.orders.values()):
            if order.status in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
                await self.cancel_order(order.client_order_id)

    async def cancel_stale_orders(self) -> None:
        now = datetime.now(UTC)
        for order in list(self.orders.values()):
            if order.status == OrderStatus.OPEN and (now - order.created_at).total_seconds() > self.settings.stale_order_seconds:
                await self.cancel_order(order.client_order_id)

    async def sync_fills(self) -> list[BotOrder]:
        """Reconcile local orders/positions against the exchange's fills.

        Replaces paper's simulate_fills for live trading. Applies only the
        incremental matched amount since the last reconciliation.
        """
        try:
            trades = self._gateway().trades()
            open_ids = self._gateway().open_order_ids()
        except Exception as exc:
            logger.error("live_sync_failed", error=str(exc))
            self.risk.record_api_error()
            return []

        aggregate: dict[str, tuple[float, float]] = {}
        for trade in trades:
            if trade.order_id not in self.orders:
                continue
            size, notional = aggregate.get(trade.order_id, (0.0, 0.0))
            aggregate[trade.order_id] = (size + trade.size, notional + trade.size * trade.price)

        updated: list[BotOrder] = []
        for order_id, order in list(self.orders.items()):
            if order.status not in {OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
                continue
            prev_size, prev_notional = self._matched.get(order_id, (0.0, 0.0))
            matched_size, matched_notional = aggregate.get(order_id, (prev_size, prev_notional))
            delta_size = matched_size - prev_size
            filled_changed = False
            if delta_size > 1e-9:
                delta_notional = matched_notional - prev_notional
                fill_price = delta_notional / delta_size if delta_size > 0 else order.price
                order.filled_size = min(order.size, order.filled_size + delta_size)
                self.inventory.apply_fill(order, delta_size, fill_price)
                self._matched[order_id] = (matched_size, matched_notional)
                order.updated_at = datetime.now(UTC)
                filled_changed = True
                logger.info(
                    "live_fill_reconciled",
                    order_id=order_id,
                    fill_size=delta_size,
                    price=fill_price,
                )
            if order.remaining_size <= 1e-9:
                order.status = OrderStatus.FILLED
            elif order_id not in open_ids:
                order.status = OrderStatus.CANCELED
            else:
                order.status = OrderStatus.PARTIALLY_FILLED if order.filled_size > 0 else OrderStatus.OPEN
            self._persist_order(order)
            if filled_changed:
                self._persist_position(order.market_id)
                _safe_persist_fill(self.session_factory, order, delta_size, fill_price)
                record_fill(self.recent_fills, order, delta_size, fill_price)
                updated.append(order)
        return updated
