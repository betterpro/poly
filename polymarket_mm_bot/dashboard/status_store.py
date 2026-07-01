from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from polymarket_mm_bot.database.orm import BotConfigRow
from polymarket_mm_bot.database.session import get_session_factory


def _get_row(session: Session) -> BotConfigRow:
    row = session.get(BotConfigRow, 1)
    if row is None:
        row = BotConfigRow(id=1, config_json={}, status_json={})
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def load_status_snapshot(session: Session | None = None) -> dict[str, Any]:
    if session is None:
        session_factory = get_session_factory()
        with session_factory() as owned:
            return dict(_get_row(owned).status_json or {})
    return dict(_get_row(session).status_json or {})


def save_status_snapshot(payload: dict[str, Any], session: Session | None = None) -> None:
    if session is None:
        session_factory = get_session_factory()
        with session_factory() as owned:
            _save_status(payload, owned)
        return
    _save_status(payload, session)


def _save_status(payload: dict[str, Any], session: Session) -> None:
    row = _get_row(session)
    row.status_json = payload
    session.commit()
