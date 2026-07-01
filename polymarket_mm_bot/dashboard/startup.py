import os

import structlog

from polymarket_mm_bot.database.migrate import run_migrations
from polymarket_mm_bot.database.orm import Base
from polymarket_mm_bot.database.session import get_engine

logger = structlog.get_logger()


def ensure_schema() -> None:
    try:
        run_migrations()
        return
    except Exception as exc:
        logger.warning("alembic_migration_failed", error=str(exc))
    try:
        Base.metadata.create_all(get_engine())
    except Exception as exc:
        logger.warning("create_all_failed", error=str(exc))


def dashboard_port() -> int:
    return int(os.environ.get("PORT", "8080"))
