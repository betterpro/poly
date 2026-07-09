from datetime import UTC, datetime, timedelta

from polymarket_mm_bot.execution import PaperExecutionEngine
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import BookLevel, BotOrder, OrderBook, Outcome, Side, Trade
from polymarket_mm_bot.risk import RiskEngine


def _print(
    price: float,
    size: float,
    seconds_from_now: float = 1.0,
    side: Side | None = None,
    token_id: str | None = None,
) -> Trade:
    return Trade(
        market_id="m1",
        token_id=token_id,
        price=price,
        size=size,
        side=side,
        timestamp=datetime.now(UTC) + timedelta(seconds=seconds_from_now),
    )


async def test_paper_fill_updates_order_and_position(settings, book):
    inventory = InventoryManager(settings)
    risk = RiskEngine(settings, inventory)
    execution = PaperExecutionEngine(settings, inventory, risk)
    order = await execution.create_order("m1", Side.BUY, 0.53, 10, "yes-token")
    fills = await execution.simulate_fills(book)
    assert fills[0].client_order_id == order.client_order_id
    assert inventory.get_position("m1").yes_size == 10


async def test_paper_fill_records_trade_feed(settings, book):
    inventory = InventoryManager(settings)
    execution = PaperExecutionEngine(settings, inventory, RiskEngine(settings, inventory))
    await execution.create_order("m1", Side.BUY, 0.53, 10, "yes-token")
    await execution.simulate_fills(book)
    assert len(execution.recent_fills) == 1
    fill = execution.recent_fills[0]
    assert fill["market_id"] == "m1"
    assert fill["side"] == "buy"
    assert fill["size"] == 10
    assert fill["value"] == round(10 * fill["price"], 6)
    assert fill["at"]


async def test_passive_buy_at_bid_does_not_fill(settings):
    inventory = InventoryManager(settings)
    risk = RiskEngine(settings, inventory)
    execution = PaperExecutionEngine(settings, inventory, risk)
    book = OrderBook(
        market_id="m1",
        token_id="yes-token",
        bids=[BookLevel(price=0.01, size=5000)],
        asks=[BookLevel(price=0.02, size=5000)],
    )
    await execution.create_order("m1", Side.BUY, 0.01, 10, "yes-token")
    fills = await execution.simulate_fills(book)
    assert fills == []
    assert inventory.get_position("m1").yes_size == 0


async def test_passive_buy_fills_when_market_prints_at_bid(settings, book):
    inventory = InventoryManager(settings)
    execution = PaperExecutionEngine(settings, inventory, RiskEngine(settings, inventory))
    # Resting bid at 0.49 (best bid), below the 0.52 ask: not a crossing order.
    await execution.create_order("m1", Side.BUY, 0.49, 10, "yes-token")
    fills = await execution.simulate_fills(book, [_print(0.49, 6)])
    assert len(fills) == 1
    assert fills[0].filled_size == 6
    assert inventory.get_position("m1").yes_size == 6


async def test_passive_buy_ignores_prints_before_order_creation(settings, book):
    inventory = InventoryManager(settings)
    execution = PaperExecutionEngine(settings, inventory, RiskEngine(settings, inventory))
    await execution.create_order("m1", Side.BUY, 0.49, 10, "yes-token")
    fills = await execution.simulate_fills(book, [_print(0.49, 6, seconds_from_now=-0.5)])
    assert fills == []
    assert inventory.get_position("m1").yes_size == 0


async def test_passive_fill_does_not_double_count_prints(settings, book):
    inventory = InventoryManager(settings)
    execution = PaperExecutionEngine(settings, inventory, RiskEngine(settings, inventory))
    await execution.create_order("m1", Side.BUY, 0.49, 10, "yes-token")
    prints = [_print(0.49, 6)]
    await execution.simulate_fills(book, prints)
    # Same trade feed seen again next cycle must not fill more.
    fills = await execution.simulate_fills(book, prints)
    assert fills == []
    assert inventory.get_position("m1").yes_size == 6


async def test_passive_buy_ignores_buyer_initiated_prints(settings, book):
    """A buyer-initiated print below our bid means someone lifted an ask —
    it cannot have hit our resting bid, so it must not fill it."""
    inventory = InventoryManager(settings)
    execution = PaperExecutionEngine(settings, inventory, RiskEngine(settings, inventory))
    await execution.create_order("m1", Side.BUY, 0.49, 10, "yes-token")
    fills = await execution.simulate_fills(book, [_print(0.49, 6, side=Side.BUY)])
    assert fills == []
    fills = await execution.simulate_fills(book, [_print(0.49, 6, seconds_from_now=2.0, side=Side.SELL)])
    assert len(fills) == 1
    assert inventory.get_position("m1").yes_size == 6


async def test_passive_fill_ignores_prints_on_other_token(settings, book):
    inventory = InventoryManager(settings)
    execution = PaperExecutionEngine(settings, inventory, RiskEngine(settings, inventory))
    await execution.create_order("m1", Side.BUY, 0.49, 10, "yes-token")
    fills = await execution.simulate_fills(book, [_print(0.40, 6, token_id="no-token")])
    assert fills == []
    fills = await execution.simulate_fills(book, [_print(0.49, 6, seconds_from_now=2.0, token_id="yes-token")])
    assert len(fills) == 1


async def test_passive_buy_ignores_prints_above_bid(settings, book):
    inventory = InventoryManager(settings)
    execution = PaperExecutionEngine(settings, inventory, RiskEngine(settings, inventory))
    await execution.create_order("m1", Side.BUY, 0.49, 10, "yes-token")
    fills = await execution.simulate_fills(book, [_print(0.52, 6)])
    assert fills == []
    assert inventory.get_position("m1").yes_size == 0


async def test_passive_sell_fills_when_market_prints_at_ask(settings, book):
    inventory = InventoryManager(settings)
    execution = PaperExecutionEngine(settings, inventory, RiskEngine(settings, inventory))
    inventory.get_position("m1").yes_size = 10
    inventory.get_position("m1").avg_yes_price = 0.45
    # Resting ask at 0.52 (best ask), above the 0.49 bid: not a crossing order.
    await execution.create_order("m1", Side.SELL, 0.52, 10, "yes-token")
    fills = await execution.simulate_fills(book, [_print(0.53, 10)])
    assert len(fills) == 1
    assert inventory.get_position("m1").yes_size == 0
    assert inventory.get_position("m1").realized_pnl > 0


def test_allowed_fill_size_caps_buy(settings):
    settings.max_position_per_market = 8
    inventory = InventoryManager(settings)
    execution = PaperExecutionEngine(settings, inventory, RiskEngine(settings, inventory))
    inventory.get_position("m1").yes_size = 6
    order = BotOrder(client_order_id="1", market_id="m1", side=Side.BUY, outcome=Outcome.YES, price=0.5, size=10)
    assert execution._allowed_fill_size(order) == 2


async def test_sell_fill_requires_inventory(settings, book):
    inventory = InventoryManager(settings)
    risk = RiskEngine(settings, inventory)
    execution = PaperExecutionEngine(settings, inventory, risk)
    await execution.create_order("m1", Side.SELL, 0.48, 10, "yes-token")
    fills = await execution.simulate_fills(book)
    assert fills == []
    inventory.get_position("m1").yes_size = 10
    inventory.get_position("m1").avg_yes_price = 0.5
    await execution.create_order("m1", Side.SELL, 0.48, 10, "yes-token")
    fills = await execution.simulate_fills(book)
    assert len(fills) == 1
    assert inventory.get_position("m1").yes_size == 0


async def test_sell_order_without_inventory_is_rejected(settings):
    inventory = InventoryManager(settings)
    risk = RiskEngine(settings, inventory)
    execution = PaperExecutionEngine(settings, inventory, risk)
    order = await execution.create_order("m1", Side.SELL, 0.55, 10, "yes-token")
    assert order.status == "rejected"
    assert order.client_order_id not in execution.orders


async def test_cancel_all_open_orders(settings):
    inventory = InventoryManager(settings)
    risk = RiskEngine(settings, inventory)
    execution = PaperExecutionEngine(settings, inventory, risk)
    await execution.create_order("m1", Side.BUY, 0.5, 10, "yes-token")
    await execution.create_order("m2", Side.SELL, 0.6, 10, "yes-token")
    await execution.cancel_all_open_orders()
    assert all(order.status.value == "canceled" for order in execution.orders.values())


async def test_paper_fill_persists_trade_row(settings, book, tmp_path):
    from polymarket_mm_bot.config import Settings
    from polymarket_mm_bot.database.orm import Base, TradeRow
    from polymarket_mm_bot.database.session import get_engine, get_session_factory

    db_settings = Settings(database_url=f"sqlite:///{tmp_path / 'fills.db'}")
    Base.metadata.create_all(get_engine(db_settings))
    factory = get_session_factory(db_settings)

    inventory = InventoryManager(settings)
    execution = PaperExecutionEngine(
        settings, inventory, RiskEngine(settings, inventory), session_factory=factory
    )
    await execution.create_order("m1", Side.BUY, 0.53, 10, "yes-token")
    fills = await execution.simulate_fills(book)
    assert len(fills) == 1

    with factory() as session:
        rows = session.query(TradeRow).all()
    assert len(rows) == 1
    assert rows[0].market_id == "m1"
    assert rows[0].side == "buy"
    assert rows[0].size == 10
    assert rows[0].price == 0.53
