"""Probe Supabase session pooler regions for a direct DATABASE_URL."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]
REGIONS = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "eu-west-1",
    "eu-west-2",
    "eu-west-3",
    "eu-central-1",
    "eu-north-1",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-northeast-1",
    "ap-northeast-2",
    "ap-south-1",
    "ca-central-1",
    "sa-east-1",
]


def try_connect(url: str, label: str) -> bool:
    try:
        engine = create_engine(
            url,
            poolclass=NullPool,
            connect_args={"connect_timeout": 5},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"OK {label}")
        return True
    except Exception as exc:
        print(f"FAIL {label} error={type(exc).__name__}: {exc}")
        return False


def main() -> int:
    cfg = dotenv_values(ROOT / ".env")
    raw = (cfg.get("DATABASE_URL") or "").strip().strip('"').strip("'")
    match = re.match(
        r"postgresql://postgres:([^@]+)@db\.([^.]+)\.supabase\.co:(5432|6543)/postgres",
        raw,
    )
    if not match:
        print("Could not parse direct Supabase DATABASE_URL", file=sys.stderr)
        return 1

    password, ref = match.group(1), match.group(2)
    candidates: list[tuple[str, str]] = []

    for region in REGIONS:
        for prefix in ("aws-0", "aws-1", "aws"):
            host = f"{prefix}-{region}.pooler.supabase.com"
            candidates.append(
                (
                    f"session {prefix}-{region}",
                    f"postgresql+psycopg://postgres.{ref}:{password}@{host}:5432/postgres"
                    "?sslmode=require&connect_timeout=5",
                )
            )
            candidates.append(
                (
                    f"transaction {prefix}-{region}",
                    f"postgresql+psycopg://postgres.{ref}:{password}@{host}:6543/postgres"
                    "?sslmode=require&connect_timeout=5",
                )
            )

    candidates.append(
        (
            f"session {ref}.pooler",
            f"postgresql+psycopg://postgres.{ref}:{password}@{ref}.pooler.supabase.com:5432/postgres"
            "?sslmode=require&connect_timeout=5",
        )
    )
    candidates.append(
        (
            f"transaction {ref}.pooler",
            f"postgresql+psycopg://postgres.{ref}:{password}@{ref}.pooler.supabase.com:6543/postgres"
            "?sslmode=require&connect_timeout=5",
        )
    )
    candidates.append(
        (
            "transaction direct host",
            f"postgresql+psycopg://postgres.{ref}:{password}@db.{ref}.supabase.co:6543/postgres"
            "?sslmode=require&connect_timeout=5",
        )
    )

    candidates.append(
        (
            "transaction direct host postgres user",
            f"postgresql+psycopg://postgres:{password}@db.{ref}.supabase.co:6543/postgres"
            "?sslmode=require&connect_timeout=5",
        )
    )
    candidates.append(
        (
            "session direct host postgres user",
            f"postgresql+psycopg://postgres:{password}@db.{ref}.supabase.co:5432/postgres"
            "?sslmode=require&connect_timeout=5",
        )
    )

    for label, url in candidates:
        if try_connect(url, label):
            safe = re.sub(r":([^:@/]+)@", ":***@", url.split("?")[0])
            print(f"POOLER_URL={safe}")
            return 0

    print("No pooler endpoint worked", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
