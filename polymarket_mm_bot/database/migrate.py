from alembic import command
from alembic.config import Config


def run_migrations() -> None:
    command.upgrade(Config("alembic.ini"), "head")
