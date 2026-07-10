"""Print a profitability report for the bot.

Usage:
    DATABASE_URL=postgresql://... python -m scripts.profit_report
    # or
    python -m scripts.profit_report "postgresql://user:pass@host:port/db"

Run it from anywhere that can reach the database (e.g. a Railway shell).
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from polymarket_mm_bot.config.db_url import normalize_database_url
from polymarket_mm_bot.reporting.profit_report import build_report, format_report


def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("Set DATABASE_URL or pass the connection string as an argument.")
    engine = create_engine(normalize_database_url(url))
    with Session(engine) as session:
        print(format_report(build_report(session)))


if __name__ == "__main__":
    main()
