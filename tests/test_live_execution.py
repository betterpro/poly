"""Live execution engine tests using a fake CLOB gateway (no real network)."""

from __future__ import annotations

import pytest

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.execution.engine import LiveExecutionEngine
from polymarket_mm_bot.execution.live_client import ExchangeTrade, PlacedOrder
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import BotOrder, OrderStatus, Outcome, Side
from polymarket_mm_bot.risk import RiskEngine


class FakeGateway:
    def __init__(self):
        self.placed: list[tuple] = []
        self.canceled: list[str] = []
        self._open: set[str] = set()
        self._trades: list[ExchangeTrade] = []
        self.balance = 5_000.0
        self.allowance = 100_000.0
        self.fail_place = False
        self._next = 0

    def place_order(self, token_id, side, price, size) -> PlacedOrder:
        if self.fail_place:
            raise RuntimeError("exchange rejected order")
        self._next += 1
        order_id = f"ex-{self._next}"
        self._open.add(order_id)
        self.placed.append((order_id, token_id, side, price, size))
        return PlacedOrder(order_id=order_id)

    def cancel(self, order_id) -> None:
        self.canceled.append(order_id)
        self._open.discard(order_id)

    def cancel_market(self, token_id) -> None:
        pass

    def open_order_ids(self) -> set[str]:
        return set(self._open)

    def trades(self) -> list[ExchangeTrade]:
        return list(self._trades)

    def collateral_balance(self) -> float:
        return self.balance

    def collateral_allowance(self) -> float:
        return self.allowance


def _live_settings(**overrides) -> Settings:
    base = dict(
        paper_trading=False,
        run_mode="live",
        live_trading_confirmed=True,
        polymarket_private_key="0xabc",
        polymarket_funder_address="0xdef",
        max_order_size=25,
        max_position_per_market=200,
        max_total_exposure=1_000,
    )
    base.update(overrides)
    return Settings(**base)


def _engine(gateway: FakeGateway, settings: Settings | None = None) -> LiveExecutionEngine:
    settings = settings or _live_settings()
    inventory = InventoryManager(settings)
    risk = RiskEngine(settings, inventory)
    return LiveExecutionEngine(settings, inventory, risk, gateway=gateway)


async def test_live_create_order_uses_exchange_id():
    gw = FakeGateway()
    engine = _engine(gw)
    order = await engine.create_order("m1", Side.BUY, 0.5, 10, "yes-token")
    assert order.status == OrderStatus.OPEN
    assert order.client_order_id == "ex-1"
    assert "ex-1" in engine.orders
    assert gw.placed[0][1] == "yes-token"
    assert gw.placed[0][2] == Side.BUY


async def test_live_order_risk_rejected_not_placed():
    gw = FakeGateway()
    engine = _engine(gw)
    order = await engine.create_order("m1", Side.BUY, 0.5, 999, "yes-token")
    assert order.status == OrderStatus.REJECTED
    assert gw.placed == []


async def test_live_missing_token_rejected():
    gw = FakeGateway()
    engine = _engine(gw)
    order = await engine.create_order("m1", Side.BUY, 0.5, 10, None)
    assert order.status == OrderStatus.REJECTED
    assert gw.placed == []


async def test_live_place_failure_records_failure():
    gw = FakeGateway()
    gw.fail_place = True
    engine = _engine(gw)
    order = await engine.create_order("m1", Side.BUY, 0.5, 10, "yes-token")
    assert order.status == OrderStatus.REJECTED
    assert engine.risk.market_failures.get("m1") == 1


async def test_live_sync_partial_then_full_fill():
    gw = FakeGateway()
    engine = _engine(gw)
    order = await engine.create_order("m1", Side.BUY, 0.5, 10, "yes-token")
    oid = order.client_order_id

    gw._trades = [ExchangeTrade(order_id=oid, price=0.5, size=4)]
    updated = await engine.sync_fills()
    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert order.filled_size == 4
    assert engine.inventory.get_position("m1").yes_size == 4
    assert len(updated) == 1

    gw._trades = [
        ExchangeTrade(order_id=oid, price=0.5, size=4),
        ExchangeTrade(order_id=oid, price=0.5, size=6),
    ]
    await engine.sync_fills()
    assert order.status == OrderStatus.FILLED
    assert order.filled_size == 10
    # No double counting: position equals total matched, not the sum of deltas twice.
    assert engine.inventory.get_position("m1").yes_size == 10


async def test_live_sync_marks_canceled_when_off_book():
    gw = FakeGateway()
    engine = _engine(gw)
    order = await engine.create_order("m1", Side.BUY, 0.5, 10, "yes-token")
    # Order leaves the book with no fills recorded.
    gw._open.discard(order.client_order_id)
    await engine.sync_fills()
    assert order.status == OrderStatus.CANCELED
    assert engine.inventory.get_position("m1").yes_size == 0


async def test_live_cancel_order():
    gw = FakeGateway()
    engine = _engine(gw)
    order = await engine.create_order("m1", Side.BUY, 0.5, 10, "yes-token")
    await engine.cancel_order(order.client_order_id)
    assert order.status == OrderStatus.CANCELED
    assert order.client_order_id in gw.canceled


def test_live_preflight_ok():
    gw = FakeGateway()
    engine = _engine(gw)
    engine.preflight()  # should not raise


def test_live_preflight_zero_balance_raises():
    gw = FakeGateway()
    gw.balance = 0
    engine = _engine(gw)
    with pytest.raises(RuntimeError, match="collateral balance"):
        engine.preflight()


def test_live_preflight_insufficient_allowance_raises():
    gw = FakeGateway()
    gw.allowance = 10  # < max_total_exposure
    engine = _engine(gw)
    with pytest.raises(RuntimeError, match="allowance"):
        engine.preflight()


async def test_live_no_double_count_across_restart():
    gw = FakeGateway()
    gw._open = {"ex-1"}
    gw._trades = [ExchangeTrade(order_id="ex-1", price=0.5, size=4)]
    # Simulate a fresh process that reloaded a partially-filled order from the DB.
    settings = _live_settings()
    inventory = InventoryManager(settings)
    reloaded = {
        "ex-1": BotOrder(
            client_order_id="ex-1",
            market_id="m1",
            token_id="yes-token",
            side=Side.BUY,
            outcome=Outcome.YES,
            price=0.5,
            size=10,
            filled_size=4,
            status=OrderStatus.PARTIALLY_FILLED,
        )
    }
    engine = LiveExecutionEngine(
        settings, inventory, RiskEngine(settings, inventory), orders=reloaded, gateway=gw
    )
    await engine.sync_fills()
    # The already-counted 4 units must not be re-applied.
    assert inventory.get_position("m1").yes_size == 0
    assert reloaded["ex-1"].filled_size == 4


async def test_live_engine_requires_confirmation():
    settings = _live_settings()
    inventory = InventoryManager(settings)
    risk = RiskEngine(settings, inventory)
    # Paper settings must never construct a live engine.
    paper = Settings(paper_trading=True)
    with pytest.raises(ValueError):
        LiveExecutionEngine(paper, inventory, risk, gateway=FakeGateway())
