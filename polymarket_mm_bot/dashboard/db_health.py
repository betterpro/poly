from sqlalchemy import text

from polymarket_mm_bot.database.orm import BotConfigRow
from polymarket_mm_bot.database.session import get_session_factory


def database_ok() -> bool:
    try:
        with get_session_factory()() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def settings_persisted() -> bool:
    try:
        with get_session_factory()() as session:
            row = session.get(BotConfigRow, 1)
            return row is not None and bool(row.config_json)
    except Exception:
        return False
