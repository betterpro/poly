from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from polymarket_mm_bot.config import Settings, get_settings


def get_engine(settings: Settings | None = None):
    settings = settings or get_settings()
    url = settings.database_url
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("postgresql"):
        kwargs["poolclass"] = NullPool
        kwargs["connect_args"] = {
            "connect_timeout": 5,
            "options": "-c statement_timeout=5000",
        }
    return create_engine(url, **kwargs)


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(settings), expire_on_commit=False)
