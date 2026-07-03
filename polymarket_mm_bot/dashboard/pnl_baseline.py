from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from sqlalchemy.orm import Session

from polymarket_mm_bot.database.orm import BotConfigRow
from polymarket_mm_bot.database.session import get_session_factory

logger = structlog.get_logger()

TRACKING_KEY = "daily_pnl_tracking"


def _utc_today() -> str:
    return datetime.now(UTC).date().isoformat()


def _get_row(session: Session) -> BotConfigRow:
    row = session.get(BotConfigRow, 1)
    if row is None:
        row = BotConfigRow(id=1, config_json={}, status_json={})
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def load_daily_pnl_tracking(session: Session | None = None) -> dict[str, Any] | None:
    if session is None:
        session_factory = get_session_factory()
        with session_factory() as owned:
            return load_daily_pnl_tracking(owned)
    config = dict(_get_row(session).config_json or {})
    tracking = config.get(TRACKING_KEY)
    return dict(tracking) if isinstance(tracking, dict) else None


def save_daily_pnl_tracking(tracking: dict[str, Any], session: Session | None = None) -> dict[str, Any]:
    if session is None:
        session_factory = get_session_factory()
        with session_factory() as owned:
            return save_daily_pnl_tracking(tracking, owned)
    row = _get_row(session)
    config = dict(row.config_json or {})
    config[TRACKING_KEY] = tracking
    row.config_json = config
    try:
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.warning("daily_pnl_tracking_save_failed", error=str(exc))
    return tracking


def resolve_daily_pnl(total_pnl: float, session: Session | None = None) -> tuple[float, float, dict[str, Any]]:
    tracking = load_daily_pnl_tracking(session)
    today = _utc_today()
    if tracking and tracking.get("day") == today and tracking.get("baseline") is not None:
        baseline = float(tracking["baseline"])
    else:
        baseline = total_pnl
        tracking = {
            "baseline": baseline,
            "day": today,
            "reset_at": datetime.now(UTC).isoformat(),
            "reset_by": "utc_day",
        }
        save_daily_pnl_tracking(tracking, session)
    return baseline, total_pnl - baseline, tracking


def reset_daily_pnl_baseline(total_pnl: float, session: Session | None = None) -> dict[str, Any]:
    today = _utc_today()
    tracking = {
        "baseline": total_pnl,
        "day": today,
        "reset_at": datetime.now(UTC).isoformat(),
        "reset_by": "manual",
    }
    save_daily_pnl_tracking(tracking, session)
    return {
        "baseline": total_pnl,
        "daily_pnl": 0.0,
        "reset_at": tracking["reset_at"],
        "reset_by": tracking["reset_by"],
    }
