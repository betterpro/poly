from __future__ import annotations

import structlog
from sqlalchemy.orm import Session, sessionmaker

from polymarket_mm_bot.config import Settings
from polymarket_mm_bot.execution import PaperExecutionEngine
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.risk import RiskEngine
from polymarket_mm_bot.database.runtime_state import load_orders, load_positions
from polymarket_mm_bot.database.session import get_session_factory

logger = structlog.get_logger()


class TradingRuntime:
    def __init__(self, settings: Settings):
        if not settings.paper_trading or settings.run_mode == "live":
            raise RuntimeError(
                "Live trading is not wired to an exchange adapter yet. "
                "Keep PAPER_TRADING=true and RUN_MODE=paper until LiveExecutionEngine is implemented."
            )
        self.settings = settings
        self.session_factory = self._build_session_factory(settings)
        positions, orders = self._load_persisted_state(self.session_factory)
        self.inventory = InventoryManager(settings, positions)
        self.risk = RiskEngine(settings, self.inventory)
        self.execution = PaperExecutionEngine(
            settings,
            self.inventory,
            self.risk,
            orders=orders,
            session_factory=self.session_factory,
        )

    def refresh_settings(self, settings: Settings) -> None:
        if not settings.paper_trading or settings.run_mode == "live":
            raise RuntimeError(
                "Live trading is not wired to an exchange adapter yet. "
                "Keep PAPER_TRADING=true and RUN_MODE=paper until LiveExecutionEngine is implemented."
            )
        self.settings = settings
        self.inventory.settings = settings
        self.risk.settings = settings
        self.execution.settings = settings

    @staticmethod
    def _build_session_factory(settings: Settings) -> sessionmaker[Session] | None:
        try:
            return get_session_factory(settings)
        except Exception as exc:
            logger.warning("runtime_session_factory_unavailable", error=str(exc))
            return None

    @staticmethod
    def _load_persisted_state(
        session_factory: sessionmaker[Session] | None,
    ) -> tuple[dict, dict]:
        if session_factory is None:
            return {}, {}
        try:
            with session_factory() as session:
                return load_positions(session), load_orders(session)
        except Exception as exc:
            logger.warning("runtime_state_load_failed", error=str(exc))
            return {}, {}


_runtime: TradingRuntime | None = None


def get_trading_runtime(settings: Settings) -> TradingRuntime:
    global _runtime
    if _runtime is None:
        _runtime = TradingRuntime(settings)
        return _runtime
    _runtime.refresh_settings(settings)
    return _runtime
