from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.orm import Session

from polymarket_mm_bot.config.runtime_settings import clear_runtime_settings_cache, get_effective_settings
from polymarket_mm_bot.config.settings import get_settings
from polymarket_mm_bot.database.orm import BotConfigRow
from polymarket_mm_bot.database.session import get_session_factory
from polymarket_mm_bot.execution.engine import LIVE_EXECUTION_IMPLEMENTED
from polymarket_mm_bot.security import totp

logger = structlog.get_logger()

_COUNTER_KEY = "live_totp_last_counter"
_MODE_AUDIT_KEY = "mode_change"


def _get_row(session: Session) -> BotConfigRow:
    row = session.get(BotConfigRow, 1)
    if row is None:
        row = BotConfigRow(id=1, config_json={}, status_json={})
        session.add(row)
        session.commit()
        session.refresh(row)
    return row


def live_prerequisites() -> dict[str, bool]:
    """Which server-side requirements for live trading are satisfied."""
    base = get_settings()
    return {
        "totp_configured": bool(base.live_totp_secret),
        "live_trading_confirmed": bool(base.live_trading_confirmed),
        "wallet_configured": bool(base.polymarket_private_key and base.polymarket_funder_address),
        "execution_implemented": LIVE_EXECUTION_IMPLEMENTED,
    }


def get_mode_state(session: Session | None = None) -> dict[str, Any]:
    effective = get_effective_settings(session)
    prereqs = live_prerequisites()
    return {
        "paper_trading": effective.paper_trading,
        "run_mode": effective.run_mode,
        "mode": "paper" if effective.paper_trading else "live",
        "prerequisites": prereqs,
        "can_go_live": all(
            prereqs[key] for key in ("totp_configured", "live_trading_confirmed", "wallet_configured")
        ),
    }


def _apply_mode(paper_trading: bool, run_mode: str, extra: dict[str, Any], session: Session) -> None:
    row = _get_row(session)
    config = dict(row.config_json or {})
    config["paper_trading"] = paper_trading
    config["run_mode"] = run_mode
    config.update(extra)
    row.config_json = config
    session.commit()
    clear_runtime_settings_cache()


def switch_to_paper(session: Session | None = None) -> dict[str, Any]:
    """Return to paper trading. Always allowed (safe direction)."""
    if session is None:
        session_factory = get_session_factory()
        with session_factory() as owned:
            return switch_to_paper(owned)
    audit = {
        "mode": "paper",
        "at": datetime.now(UTC).isoformat(),
        "by": "dashboard",
    }
    _apply_mode(True, "paper", {_MODE_AUDIT_KEY: audit}, session)
    logger.warning("trading_mode_changed", mode="paper")
    return get_mode_state(session)


def switch_to_live(code: str, session: Session | None = None) -> dict[str, Any]:
    """Switch to live trading after verifying an authenticator code.

    Raises ValueError (with a user-facing message) if any prerequisite or the
    TOTP code is missing/invalid, so nothing is persisted on failure.
    """
    if session is None:
        session_factory = get_session_factory()
        with session_factory() as owned:
            return switch_to_live(code, owned)

    base = get_settings()
    if not base.live_totp_secret:
        raise ValueError("Authenticator (TOTP) is not configured on the server. Set LIVE_TOTP_SECRET.")
    if not base.live_trading_confirmed:
        raise ValueError("Live trading requires LIVE_TRADING_CONFIRMED=true in the server environment.")
    if not base.polymarket_private_key or not base.polymarket_funder_address:
        raise ValueError("Live trading requires wallet credentials in the server environment.")

    counter = totp.matched_counter(base.live_totp_secret, code)
    if counter is None:
        logger.warning("live_switch_rejected", reason="invalid_totp")
        raise ValueError("Invalid authenticator code.")

    row = _get_row(session)
    config = dict(row.config_json or {})
    last_counter = config.get(_COUNTER_KEY)
    if isinstance(last_counter, int) and counter <= last_counter:
        logger.warning("live_switch_rejected", reason="totp_replay")
        raise ValueError("This authenticator code was already used. Wait for a new code.")

    audit = {
        "mode": "live",
        "at": datetime.now(UTC).isoformat(),
        "by": "dashboard",
    }
    _apply_mode(False, "live", {_COUNTER_KEY: counter, _MODE_AUDIT_KEY: audit}, session)
    logger.warning("trading_mode_changed", mode="live")
    state = get_mode_state(session)
    if not LIVE_EXECUTION_IMPLEMENTED:
        state["warning"] = (
            "Mode set to LIVE, but the live execution engine is not implemented yet. "
            "The bot will report 'live_unavailable' and place no orders until it is built."
        )
    return state
