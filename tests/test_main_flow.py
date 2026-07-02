from polymarket_mm_bot import main as bot_main
from polymarket_mm_bot.config import Settings
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
