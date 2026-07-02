from __future__ import annotations

import structlog

from polymarket_mm_bot.database.orm import PositionRow
from polymarket_mm_bot.database.session import get_session_factory
from polymarket_mm_bot.inventory.manager import InventoryManager

logger = structlog.get_logger()


def load_positions(inventory: InventoryManager) -> None:
    """Rehydrate in-memory positions from the database on startup.

    Without this, a restart or crash resets exposure and realized-PnL tracking to
    zero, which would let the bot silently blow through its risk limits.
    """
    try:
        session_factory = get_session_factory()
        with session_factory() as session:
            rows = session.query(PositionRow).all()
            for row in rows:
                position = inventory.get_position(row.market_id)
                position.yes_size = row.yes_size
                position.no_size = row.no_size
                position.realized_pnl = row.realized_pnl
                position.avg_yes_price = row.avg_yes_price
                position.avg_no_price = row.avg_no_price
        logger.info("positions_loaded", count=len(inventory.positions))
    except Exception as exc:  # pragma: no cover - defensive: DB may be unavailable
        logger.warning("positions_load_failed", error=str(exc))


def save_positions(inventory: InventoryManager) -> None:
    """Persist in-memory positions so risk state survives a restart."""
    try:
        session_factory = get_session_factory()
        with session_factory() as session:
            for market_id, position in inventory.positions.items():
                if not market_id:
                    continue
                row = session.get(PositionRow, market_id)
                if row is None:
                    row = PositionRow(market_id=market_id)
                    session.add(row)
                row.yes_size = position.yes_size
                row.no_size = position.no_size
                row.realized_pnl = position.realized_pnl
                row.avg_yes_price = position.avg_yes_price
                row.avg_no_price = position.avg_no_price
            session.commit()
    except Exception as exc:  # pragma: no cover - defensive: DB may be unavailable
        logger.warning("positions_save_failed", error=str(exc))
