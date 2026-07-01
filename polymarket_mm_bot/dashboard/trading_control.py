from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from polymarket_mm_bot.database.orm import BotConfigRow
from polymarket_mm_bot.database.session import get_session_factory

CONTROL_KEY = "trading_control"


def _get_row(session: Session) -> BotConfigRow:
    row = session.get(BotConfigRow, 1)
    if row is None:
        row = BotConfigRow(id=1, config_json={}, status_json={})
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def load_trading_control(session: Session | None = None) -> dict[str, Any]:
    if session is None:
        session_factory = get_session_factory()
        with session_factory() as owned:
            return load_trading_control(owned)
    config = dict(_get_row(session).config_json or {})
    control = config.get(CONTROL_KEY)
    if isinstance(control, dict):
        return dict(control)
    return {"enabled": True}


def save_trading_control(control: dict[str, Any], session: Session | None = None) -> dict[str, Any]:
    if session is None:
        session_factory = get_session_factory()
        with session_factory() as owned:
            return save_trading_control(control, owned)
    row = _get_row(session)
    config = dict(row.config_json or {})
    config[CONTROL_KEY] = control
    row.config_json = config
    session.commit()
    return control


def is_trading_enabled(session: Session | None = None) -> bool:
    return bool(load_trading_control(session).get("enabled", True))


def set_trading_enabled(enabled: bool, session: Session | None = None) -> dict[str, Any]:
    control = {
        "enabled": enabled,
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": "manual",
    }
    save_trading_control(control, session)
    return control


def stop_trading(session: Session | None = None) -> dict[str, Any]:
    return set_trading_enabled(False, session)


def resume_trading(session: Session | None = None) -> dict[str, Any]:
    return set_trading_enabled(True, session)
