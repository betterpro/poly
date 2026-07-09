from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from polymarket_mm_bot.config.runtime_settings import clear_runtime_settings_cache
from polymarket_mm_bot.database.orm import (
    BotConfigRow,
    BotOrderRow,
    MarketRow,
    MarketScoreRow,
    OrderBookRow,
    PnlSnapshotRow,
    PositionRow,
    RiskEventRow,
    StrategySignalRow,
    TradeRow,
)
from polymarket_mm_bot.database.session import get_session_factory


RUNTIME_TABLES = (
    BotOrderRow,
    PositionRow,
    PnlSnapshotRow,
    RiskEventRow,
    StrategySignalRow,
    MarketScoreRow,
    TradeRow,
    OrderBookRow,
    MarketRow,
)


def clean_runtime_database(session: Session | None = None) -> dict[str, Any]:
    if session is None:
        session_factory = get_session_factory()
        with session_factory() as owned:
            return clean_runtime_database(owned)

    deleted: dict[str, int] = {}
    try:
        for model in RUNTIME_TABLES:
            count = session.query(model).delete(synchronize_session=False)
            deleted[model.__tablename__] = int(count or 0)

        row = session.get(BotConfigRow, 1)
        if row is None:
            row = BotConfigRow(id=1, config_json={}, status_json={})
            session.add(row)

        config = dict(row.config_json or {})
        now = datetime.now(UTC).isoformat()
        config["daily_pnl_tracking"] = {
            "baseline": 0,
            "day": datetime.now(UTC).date().isoformat(),
            "reset_at": now,
            "reset_by": "database_clean",
        }
        config["trading_control"] = {
            "enabled": False,
            "updated_at": now,
            "updated_by": "database_clean",
        }
        row.config_json = config
        row.status_json = {}
        session.commit()
    except Exception:
        session.rollback()
        raise

    clear_runtime_settings_cache()
    return {
        "ok": True,
        "trading_enabled": False,
        "deleted": deleted,
    }
