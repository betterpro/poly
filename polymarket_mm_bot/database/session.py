from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from polymarket_mm_bot.config import Settings, get_settings


def get_engine(settings: Settings | None = None):
    settings = settings or get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True)


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(settings), expire_on_commit=False)
