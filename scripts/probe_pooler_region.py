"""Find Supabase project region via direct connection metadata."""
from __future__ import annotations

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from polymarket_mm_bot.config.db_url import normalize_database_url

cfg = dotenv_values(".env")
url = normalize_database_url(cfg["DATABASE_URL"]).replace(":6543/", ":5432/")
engine = create_engine(url, poolclass=NullPool)

queries = [
    "SELECT version()",
    "SELECT inet_server_addr()::text",
    "SELECT current_setting('server_version')",
    "SELECT name, setting FROM pg_settings WHERE name ILIKE '%region%' OR name ILIKE '%rds%' OR name ILIKE '%cloud%' LIMIT 20",
]

with engine.connect() as conn:
    for q in queries:
        print("---", q)
        try:
            rows = conn.execute(text(q)).fetchall()
            for row in rows:
                print(row)
        except Exception as exc:
            print("error:", exc)
