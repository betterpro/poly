from polymarket_mm_bot import main as bot_main
from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.execution import PaperExecutionEngine
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import BotOrder, Side
from polymarket_mm_bot.risk import RiskEngine
from polymarket_mm_bot.risk.engine import RiskDecision


class _FakeRisk:
    def __init__(self):
        self.api_errors = 0

    def record_api_error(self):
        self.api_errors += 1
        return RiskDecision(True)


class _FakeExecution:
    def __init__(self):
        self.orders = {}
        self.canceled = False

    async def cancel_all_open_orders(self):
        self.canceled = True


class _FakeRuntime:
    def __init__(self):
        self.inventory = None
        self.risk = _FakeRisk()
        self.execution = _FakeExecution()
        self.session_factory = None


class _FailingDataClient:
    def __init__(self, settings):
        self.settings = settings

    async def fetch_active_markets(self, categories=None):
        raise RuntimeError("gamma unavailable")

    async def close(self):
        return None


async def test_run_once_cancels_orders_and_records_api_error(monkeypatch):
    runtime = _FakeRuntime()
    monkeypatch.setattr(bot_main, "get_effective_settings", lambda: Settings())
    monkeypatch.setattr(bot_main, "get_trading_runtime", lambda settings: runtime)
    monkeypatch.setattr(bot_main, "PolymarketDataClient", _FailingDataClient)
    monkeypatch.setattr(bot_main, "is_trading_enabled", lambda: True)
    monkeypatch.setattr(bot_main, "save_status_snapshot", lambda payload: None)

    await bot_main.run_once()

    assert runtime.execution.canceled is True
    assert runtime.risk.api_errors == 1
    assert bot_main.state.bot_status == "api_error"
    assert bot_main.state.trading_enabled is False
    assert bot_main.state.risk_events[-1]["code"] == "api_error"


async def test_unwind_quotes_sell_for_position_in_unselected_market(settings, market, book):
    inventory = InventoryManager(settings)
    execution = PaperExecutionEngine(settings, inventory, RiskEngine(settings, inventory))
    inventory.get_position("m1").yes_size = 10
    inventory.get_position("m1").avg_yes_price = 0.45

    # Market holds inventory but is no longer in the selected set.
    await bot_main._unwind_orphaned_positions(
        settings, inventory, execution, [market], [], {"m1": book}, {"m1": []}
    )

    sells = [o for o in execution.orders.values() if o.side == Side.SELL]
    assert len(sells) == 1
    assert sells[0].price == 0.51  # one tick inside the 0.52 best ask
    assert sells[0].size == 10


async def test_unwind_cancels_buy_orders_for_unselected_position(settings, market, book):
    inventory = InventoryManager(settings)
    execution = PaperExecutionEngine(
        settings,
        inventory,
        RiskEngine(settings, inventory),
        orders={
            "buy": BotOrder(
                client_order_id="buy",
                market_id="m1",
                token_id="yes-token",
                side=Side.BUY,
                price=0.49,
                size=10,
            )
        },
    )
    inventory.get_position("m1").yes_size = 10
    inventory.get_position("m1").avg_yes_price = 0.45

    await bot_main._unwind_orphaned_positions(
        settings, inventory, execution, [market], [], {"m1": book}, {"m1": []}
    )

    assert execution.orders["buy"].status == "canceled"
    sells = [o for o in execution.orders.values() if o.side == Side.SELL]
    assert len(sells) == 1


async def test_unwind_exits_sub_penny_longshot_position(settings, market):
    from polymarket_mm_bot.models import BookLevel, OrderBook

    inventory = InventoryManager(settings)
    execution = PaperExecutionEngine(settings, inventory, RiskEngine(settings, inventory))
    inventory.get_position("m1").yes_size = 10
    inventory.get_position("m1").avg_yes_price = 0.01
    book = OrderBook(
        market_id="m1",
        token_id="yes-token",
        bids=[BookLevel(price=0.008, size=5000)],
        asks=[BookLevel(price=0.009, size=5000)],
    )

    await bot_main._unwind_orphaned_positions(
        settings, inventory, execution, [market], [], {"m1": book}, {"m1": []}
    )

    # The exit is quoted below one cent, crossing the bid, so it fills at once.
    assert inventory.get_position("m1").yes_size == 0


async def test_unwind_skips_selected_markets(settings, market, book):
    inventory = InventoryManager(settings)
    execution = PaperExecutionEngine(settings, inventory, RiskEngine(settings, inventory))
    inventory.get_position("m1").yes_size = 10

    await bot_main._unwind_orphaned_positions(
        settings, inventory, execution, [market], [market], {"m1": book}, {"m1": []}
    )

    assert not execution.orders
