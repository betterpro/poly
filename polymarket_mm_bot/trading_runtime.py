from __future__ import annotations

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.execution import PaperExecutionEngine
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.risk import RiskEngine


class TradingRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.inventory = InventoryManager(settings)
        self.risk = RiskEngine(settings, self.inventory)
        self.execution = PaperExecutionEngine(settings, self.inventory, self.risk)

    def refresh_settings(self, settings: Settings) -> None:
        self.settings = settings
        self.inventory.settings = settings
        self.risk.settings = settings
        self.execution.settings = settings


_runtime: TradingRuntime | None = None


def get_trading_runtime(settings: Settings) -> TradingRuntime:
    global _runtime
    if _runtime is None:
        _runtime = TradingRuntime(settings)
        return _runtime
    _runtime.refresh_settings(settings)
    return _runtime
