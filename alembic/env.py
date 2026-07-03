from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from polymarket_mm_bot.config import get_settings
from polymarket_mm_bot.database.orm import Base
from polymarket_mm_bot.config.db_url import normalize_database_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = normalize_database_url(get_settings().database_url)
config.set_main_option("sqlalchemy.url", database_url)
target_metadata = Base.metadata


def _migration_engine():
    kwargs: dict = {"poolclass": pool.NullPool}
    if database_url.startswith("postgresql"):
        kwargs["connect_args"] = {
            "connect_timeout": 5,
            "target_session_attrs": "read-write",
            "options": "-c statement_timeout=30000",
        }
    return create_engine(database_url, **kwargs)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = _migration_engine()
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
