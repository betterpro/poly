from __future__ import annotations

import base64
import binascii
import secrets
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from polymarket_mm_bot.config.runtime_settings import (
    EditableBotSettings,
    get_editable_settings,
    save_editable_settings,
)
from polymarket_mm_bot.config.settings import get_settings
from polymarket_mm_bot.dashboard.database_reset import clean_runtime_database
from polymarket_mm_bot.dashboard.db_health import database_ok, settings_persisted
from polymarket_mm_bot.dashboard.pages import DASHBOARD_HTML
from polymarket_mm_bot.dashboard.snapshot_cache import (
    cache_age_seconds,
    get_cached_snapshot,
    start_snapshot_poller,
    stop_snapshot_poller,
)
from polymarket_mm_bot.dashboard.pnl_baseline import load_daily_pnl_tracking, reset_daily_pnl_baseline
from polymarket_mm_bot.dashboard.trading_control import load_trading_control, resume_trading, stop_trading
from polymarket_mm_bot.dashboard.startup import ensure_schema
from polymarket_mm_bot.database.runtime_state import load_daily_pnl_history
from polymarket_mm_bot.database.session import get_session_factory
from polymarket_mm_bot.reporting.optimizer import build_optimizer_report
from polymarket_mm_bot.utils import market_dict_matches_categories

logger = structlog.get_logger()


_PUBLIC_PATHS = frozenset({"/health"})
_UNAUTHORIZED = Response(
    content='{"detail":"Unauthorized"}',
    status_code=401,
    media_type="application/json",
    headers={"WWW-Authenticate": 'Basic realm="polymarket-mm-bot"'},
)


def _basic_auth_ok(header: str | None, username: str, password: str) -> bool:
    if not header or not header.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(header[len("Basic ") :]).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return False
    user, sep, pw = decoded.partition(":")
    if not sep:
        return False
    # Evaluate both comparisons to avoid short-circuit timing leaks.
    user_ok = secrets.compare_digest(user, username)
    pw_ok = secrets.compare_digest(pw, password)
    return user_ok and pw_ok


def _status() -> dict[str, Any]:
    return get_cached_snapshot()


def _filter_markets(markets: list[dict[str, Any]], allowed_categories: list[str]) -> list[dict[str, Any]]:
    if not allowed_categories:
        return markets
    allowed = {category.lower() for category in allowed_categories}
    filtered: list[dict[str, Any]] = []
    for market in markets:
        if market_dict_matches_categories(market, allowed):
            filtered.append(market)
    return filtered


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_order_payload(order: dict[str, Any]) -> dict[str, Any]:
    payload = dict(order)
    size = _as_float(payload.get("size"))
    filled = _as_float(payload.get("filled_size"))
    price = _as_float(payload.get("price"))
    remaining = max(size - filled, 0.0)
    payload["remaining_size"] = round(_as_float(payload.get("remaining_size"), remaining), 6)
    payload["notional"] = round(_as_float(payload.get("notional"), size * price), 6)
    payload["filled_notional"] = round(_as_float(payload.get("filled_notional"), filled * price), 6)
    payload["remaining_notional"] = round(_as_float(payload.get("remaining_notional"), remaining * price), 6)
    return payload


def _normalize_position_payload(position: dict[str, Any]) -> dict[str, Any]:
    payload = dict(position)
    yes_size = _as_float(payload.get("yes_size"))
    no_size = _as_float(payload.get("no_size"))
    avg_yes_price = _as_float(payload.get("avg_yes_price"))
    avg_no_price = _as_float(payload.get("avg_no_price"))
    realized = _as_float(payload.get("realized_pnl"))
    unrealized = _as_float(payload.get("unrealized_pnl"))
    payload["net_yes"] = round(_as_float(payload.get("net_yes"), yes_size - no_size), 6)
    payload["gross_exposure"] = round(
        _as_float(payload.get("gross_exposure"), abs(yes_size * avg_yes_price) + abs(no_size * avg_no_price)),
        6,
    )
    payload["unrealized_pnl"] = round(unrealized, 4)
    payload["total_pnl"] = round(_as_float(payload.get("total_pnl"), realized + unrealized), 4)
    payload["mark_missing"] = bool(payload.get("mark_missing", False))
    return payload


def _normalized_pnl(snapshot: dict[str, Any]) -> dict[str, float]:
    realized = _as_float(snapshot.get("realized_pnl"))
    unrealized = _as_float(snapshot.get("unrealized_pnl"))
    total = _as_float(snapshot.get("total_pnl"), realized + unrealized)
    if abs(total - (realized + unrealized)) > 0.001:
        total = realized + unrealized
    return {"realized": realized, "unrealized": unrealized, "total": total}


def _fill_notional(fill: dict[str, Any]) -> float:
    value = _as_float(fill.get("value"))
    if value:
        return value
    return _as_float(fill.get("size")) * _as_float(fill.get("price"))


def _compute_pnl_summary(snapshot: dict[str, Any], starting_capital: float) -> dict[str, float]:
    pnl_values = _normalized_pnl(snapshot)
    realized = pnl_values["realized"]
    unrealized = pnl_values["unrealized"]
    total = pnl_values["total"]

    position_credit = sum(
        _as_float(_normalize_position_payload(dict(position)).get("gross_exposure"))
        for position in snapshot.get("positions", [])
    )
    open_order_credit = 0.0
    for order in snapshot.get("orders", []):
        side = str(order.get("side", "")).lower()
        status = str(order.get("status", "")).lower()
        if side != "buy" or status not in {"open", "partially_filled"}:
            continue
        open_order_credit += _as_float(_normalize_order_payload(dict(order)).get("remaining_notional"))

    total_bought = 0.0
    total_sold = 0.0
    for fill in snapshot.get("recent_fills", []):
        notional = _fill_notional(fill)
        side = str(fill.get("side", "")).lower()
        if side == "buy":
            total_bought += notional
        elif side == "sell":
            total_sold += notional

    capital_deployed = position_credit + open_order_credit
    return {
        "profit": round(max(0.0, realized) + max(0.0, unrealized), 4),
        "loss": round(abs(min(0.0, realized)) + abs(min(0.0, unrealized)), 4),
        "position_credit": round(position_credit, 4),
        "open_order_credit": round(open_order_credit, 4),
        "capital_deployed": round(capital_deployed, 4),
        "total_bought": round(total_bought, 4),
        "total_sold": round(total_sold, 4),
        "starting_capital": round(starting_capital, 4),
        "available_credit": round(starting_capital + total - capital_deployed, 4),
    }


def _build_pnl_payload(snapshot: dict[str, Any], starting_capital: float) -> dict[str, Any]:
    pnl_values = _normalized_pnl(snapshot)
    realized = pnl_values["realized"]
    unrealized = pnl_values["unrealized"]
    total = pnl_values["total"]
    tracking = load_daily_pnl_tracking()
    if tracking and tracking.get("baseline") is not None:
        daily_pnl = total - _as_float(tracking.get("baseline"))
    else:
        daily_pnl = _as_float(snapshot.get("daily_pnl"))
    return {
        "daily_pnl": daily_pnl,
        "total_pnl": total,
        "realized_pnl": realized,
        "unrealized_pnl": unrealized,
        "daily_pnl_reset_at": snapshot.get("daily_pnl_reset_at") or (tracking or {}).get("reset_at"),
        "daily_pnl_baseline": (tracking or {}).get("baseline"),
        **_compute_pnl_summary(snapshot, starting_capital),
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("dashboard_startup_begin")
    ensure_schema()
    start_snapshot_poller()
    logger.info("dashboard_startup_complete")
    yield
    stop_snapshot_poller()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    dashboard_username = settings.dashboard_username
    dashboard_password = settings.dashboard_password

    @app.middleware("http")
    async def _require_auth(request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)
        if not dashboard_password:
            # Fail closed: refuse to serve anything until a password is configured,
            # so a misconfigured deployment can never expose trading controls.
            logger.error("dashboard_auth_not_configured", path=request.url.path)
            return JSONResponse(
                {"detail": "Dashboard authentication is not configured. Set DASHBOARD_PASSWORD."},
                status_code=503,
            )
        if not _basic_auth_ok(request.headers.get("Authorization"), dashboard_username, dashboard_password):
            return _UNAUTHORIZED
        return await call_next(request)

    @app.get("/", response_class=HTMLResponse)
    async def root() -> str:
        return DASHBOARD_HTML

    @app.get("/health")
    async def health() -> dict:
        snapshot = _status()
        allowed = snapshot.get("allowed_categories") or settings.allowed_categories
        age = cache_age_seconds()
        control = load_trading_control()
        trading_enabled = control.get("enabled", True)
        return {
            "ok": True,
            "status": snapshot.get("bot_status", "idle"),
            "mode_warning": snapshot.get("mode_warning", settings.mode_warning),
            "allowed_categories": allowed,
            "updated_at": snapshot.get("updated_at"),
            "snapshot_age_seconds": age,
            "trading_enabled": trading_enabled,
            "bot_trading_enabled": snapshot.get("trading_enabled", trading_enabled),
            "trading_updated_at": control.get("updated_at"),
        }

    @app.get("/settings/status")
    async def settings_status() -> dict:
        ok = database_ok()
        return {
            "database_ok": ok,
            "settings_persisted": settings_persisted() if ok else False,
            "message": None
            if ok
            else (
                "Database unreachable. Set DATABASE_URL to the Railway Postgres private URL "
                "(${{Postgres.DATABASE_PRIVATE_URL}}) in project variables."
            ),
        }

    @app.get("/settings/categories")
    async def category_options() -> dict:
        from polymarket_mm_bot.utils import MARKET_CATEGORIES

        return {"categories": list(MARKET_CATEGORIES)}

    @app.get("/settings", response_model=EditableBotSettings)
    async def read_settings() -> EditableBotSettings:
        return get_editable_settings()

    @app.put("/settings", response_model=EditableBotSettings)
    async def update_settings(payload: EditableBotSettings) -> EditableBotSettings:
        if not database_ok():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Database unreachable. Set DATABASE_URL to the Railway Postgres private URL "
                    "(${{Postgres.DATABASE_PRIVATE_URL}}) in project variables."
                ),
            )
        try:
            return save_editable_settings(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.warning("settings_save_failed", error=str(exc))
            raise HTTPException(
                status_code=503,
                detail="Could not save settings. Check DATABASE_URL and Railway Postgres access.",
            ) from exc

    @app.post("/settings/clean-database")
    async def clean_database() -> dict:
        if not database_ok():
            raise HTTPException(status_code=503, detail="Database unreachable.")
        try:
            return clean_runtime_database()
        except Exception as exc:
            logger.warning("database_clean_failed", error=str(exc))
            raise HTTPException(status_code=503, detail="Could not clean database.") from exc

    @app.get("/markets")
    async def markets():
        # The full active-markets list is no longer persisted (it was unused by the
        # UI and dominated DB egress); fall back to the quoted markets, which are.
        snapshot = _status()
        allowed = snapshot.get("allowed_categories") or settings.allowed_categories
        rows = snapshot.get("active_markets") or snapshot.get("selected_markets", [])
        return _filter_markets(rows, allowed)

    @app.get("/selected-markets")
    async def selected_markets():
        snapshot = _status()
        allowed = snapshot.get("allowed_categories") or settings.allowed_categories
        return _filter_markets(snapshot.get("selected_markets", []), allowed)

    @app.get("/positions")
    async def positions():
        return [_normalize_position_payload(position) for position in _status().get("positions", [])]

    @app.get("/orders")
    async def orders():
        return [_normalize_order_payload(order) for order in _status().get("orders", [])]

    @app.get("/pnl")
    async def pnl() -> dict:
        snapshot = _status()
        return _build_pnl_payload(snapshot, settings.starting_capital)

    @app.get("/pnl/daily")
    async def daily_pnl(days: int = 30) -> dict:
        if not database_ok():
            raise HTTPException(status_code=503, detail="Database unreachable.")
        bounded_days = min(max(days, 2), 90)
        try:
            session_factory = get_session_factory()
            with session_factory() as session:
                history = load_daily_pnl_history(session, limit=bounded_days)
        except Exception as exc:
            logger.warning("daily_pnl_history_failed", error=str(exc))
            raise HTTPException(status_code=503, detail="Could not load daily PnL history.") from exc
        return {"days": history}

    @app.get("/performance/optimizer")
    async def performance_optimizer(limit: int = 20) -> dict:
        if not database_ok():
            raise HTTPException(status_code=503, detail="Database unreachable.")
        bounded_limit = min(max(limit, 1), 100)
        try:
            session_factory = get_session_factory()
            with session_factory() as session:
                return build_optimizer_report(session, limit=bounded_limit)
        except Exception as exc:
            logger.warning("optimizer_report_failed", error=str(exc))
            raise HTTPException(status_code=503, detail="Could not load optimizer report.") from exc

    @app.post("/pnl/reset-daily")
    async def reset_daily_pnl() -> dict:
        if not database_ok():
            raise HTTPException(status_code=503, detail="Database unreachable.")
        snapshot = _status()
        total = _normalized_pnl(snapshot)["total"]
        try:
            result = reset_daily_pnl_baseline(total)
        except Exception as exc:
            logger.warning("daily_pnl_reset_failed", error=str(exc))
            raise HTTPException(status_code=503, detail="Could not reset daily PnL baseline.") from exc
        return {
            **result,
            **_build_pnl_payload(snapshot, settings.starting_capital),
        }

    @app.get("/trading/status")
    async def trading_status() -> dict:
        control = load_trading_control()
        snapshot = _status()
        return {
            "trading_enabled": control.get("enabled", True),
            "updated_at": control.get("updated_at"),
            "bot_status": snapshot.get("bot_status", "idle"),
        }

    @app.post("/trading/stop")
    async def trading_stop() -> dict:
        if not database_ok():
            raise HTTPException(status_code=503, detail="Database unreachable.")
        try:
            control = stop_trading()
        except Exception as exc:
            logger.warning("trading_stop_failed", error=str(exc))
            raise HTTPException(status_code=503, detail="Could not stop trading.") from exc
        return {"trading_enabled": False, **control}

    @app.post("/trading/resume")
    async def trading_resume() -> dict:
        if not database_ok():
            raise HTTPException(status_code=503, detail="Database unreachable.")
        try:
            control = resume_trading()
        except Exception as exc:
            logger.warning("trading_resume_failed", error=str(exc))
            raise HTTPException(status_code=503, detail="Could not resume trading.") from exc
        return {"trading_enabled": True, **control}

    @app.get("/trading/mode")
    async def trading_mode() -> dict:
        from polymarket_mm_bot.dashboard.mode_control import get_mode_state

        if not database_ok():
            raise HTTPException(status_code=503, detail="Database unreachable.")
        try:
            return get_mode_state()
        except Exception as exc:
            logger.warning("trading_mode_read_failed", error=str(exc))
            raise HTTPException(status_code=503, detail="Could not read trading mode.") from exc

    @app.post("/trading/mode/live")
    async def trading_mode_live(payload: dict) -> dict:
        from polymarket_mm_bot.dashboard.mode_control import switch_to_live

        if not database_ok():
            raise HTTPException(status_code=503, detail="Database unreachable.")
        code = str(payload.get("code", "")).strip()
        try:
            return switch_to_live(code)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            logger.warning("trading_mode_live_failed", error=str(exc))
            raise HTTPException(status_code=503, detail="Could not switch to live trading.") from exc

    @app.post("/trading/mode/paper")
    async def trading_mode_paper() -> dict:
        from polymarket_mm_bot.dashboard.mode_control import switch_to_paper

        if not database_ok():
            raise HTTPException(status_code=503, detail="Database unreachable.")
        try:
            return switch_to_paper()
        except Exception as exc:
            logger.warning("trading_mode_paper_failed", error=str(exc))
            raise HTTPException(status_code=503, detail="Could not switch to paper trading.") from exc

    @app.get("/fills")
    async def fills():
        # Newest first for the dashboard trade feed.
        return list(reversed(_status().get("recent_fills", [])))

    @app.get("/risk-events")
    async def risk_events():
        return _status().get("risk_events", [])

    @app.get("/strategy-status")
    async def strategy_status():
        return _status().get("strategy_status", {})

    @app.get("/strategy-profiles")
    async def strategy_profiles():
        return _status().get("strategy_profiles", [])

    return app


app = create_app()
