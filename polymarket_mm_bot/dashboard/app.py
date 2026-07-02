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
from polymarket_mm_bot.dashboard.status_store import load_status_snapshot
from polymarket_mm_bot.dashboard.startup import ensure_schema
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


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schema()
    start_snapshot_poller()
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
        return {
            "ok": True,
            "status": snapshot.get("bot_status", "idle"),
            "mode_warning": snapshot.get("mode_warning", settings.mode_warning),
            "allowed_categories": allowed,
            "updated_at": snapshot.get("updated_at"),
            "snapshot_age_seconds": age,
            "trading_enabled": snapshot.get("trading_enabled", control.get("enabled", True)),
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
                "Database unreachable. In DigitalOcean, set DATABASE_URL to the Supabase "
                "Session pooler URI and allow external connections in Supabase network settings."
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
                    "Database unreachable. Use Supabase Session pooler DATABASE_URL in "
                    "DigitalOcean and disable network restrictions."
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
                detail="Could not save settings. Check DATABASE_URL and Supabase access.",
            ) from exc

    @app.get("/markets")
    async def markets():
        snapshot = _status()
        allowed = snapshot.get("allowed_categories") or settings.allowed_categories
        return _filter_markets(snapshot.get("active_markets", []), allowed)

    @app.get("/selected-markets")
    async def selected_markets():
        snapshot = _status()
        allowed = snapshot.get("allowed_categories") or settings.allowed_categories
        return _filter_markets(snapshot.get("selected_markets", []), allowed)

    @app.get("/positions")
    async def positions():
        return _status().get("positions", [])

    @app.get("/orders")
    async def orders():
        return _status().get("orders", [])

    @app.get("/pnl")
    async def pnl() -> dict:
        snapshot = _status()
        realized = float(snapshot.get("realized_pnl", 0.0) or 0.0)
        unrealized = float(snapshot.get("unrealized_pnl", 0.0) or 0.0)
        total = float(snapshot.get("total_pnl", realized + unrealized) or 0.0)
        if abs(total - (realized + unrealized)) > 0.001:
            total = realized + unrealized
        tracking = load_daily_pnl_tracking()
        return {
            "daily_pnl": snapshot.get("daily_pnl", 0.0),
            "total_pnl": total,
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
            "daily_pnl_reset_at": snapshot.get("daily_pnl_reset_at") or (tracking or {}).get("reset_at"),
            "daily_pnl_baseline": (tracking or {}).get("baseline"),
        }

    @app.post("/pnl/reset-daily")
    async def reset_daily_pnl() -> dict:
        if not database_ok():
            raise HTTPException(status_code=503, detail="Database unreachable.")
        snapshot = _status()
        realized = float(snapshot.get("realized_pnl", 0.0) or 0.0)
        unrealized = float(snapshot.get("unrealized_pnl", 0.0) or 0.0)
        total = float(snapshot.get("total_pnl", realized + unrealized) or 0.0)
        if abs(total - (realized + unrealized)) > 0.001:
            total = realized + unrealized
        try:
            result = reset_daily_pnl_baseline(total)
        except Exception as exc:
            logger.warning("daily_pnl_reset_failed", error=str(exc))
            raise HTTPException(status_code=503, detail="Could not reset daily PnL baseline.") from exc
        return {
            **result,
            "total_pnl": total,
            "realized_pnl": realized,
            "unrealized_pnl": unrealized,
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

    @app.get("/risk-events")
    async def risk_events():
        return _status().get("risk_events", [])

    @app.get("/strategy-status")
    async def strategy_status():
        return _status().get("strategy_status", {})

    return app


app = create_app()
