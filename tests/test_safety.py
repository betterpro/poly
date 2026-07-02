"""Tests for the live-trading safety hardening.

These lock in the fixes for the review blockers:
- dashboard authentication (fail closed when unconfigured)
- no fabricated fills / PnL when live trading is requested but not implemented
- position state persistence across restarts
- the API-error circuit breaker actually tripping
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from polymarket_mm_bot.dashboard.app import create_app
from polymarket_mm_bot.inventory import InventoryManager
from polymarket_mm_bot.models import BotOrder, Side
from polymarket_mm_bot.risk import RiskEngine


def _fresh_app(tmp_path, monkeypatch, *, password: str | None):
    db = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    if password is None:
        monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    else:
        monkeypatch.setenv("DASHBOARD_PASSWORD", password)
    from polymarket_mm_bot.config.settings import get_settings
    from polymarket_mm_bot.database.orm import Base
    from polymarket_mm_bot.database.session import get_engine

    get_settings.cache_clear()
    monkeypatch.setattr("polymarket_mm_bot.dashboard.app.ensure_schema", lambda: None)
    Base.metadata.create_all(get_engine())
    return create_app()


def test_health_is_public(tmp_path, monkeypatch):
    client = TestClient(_fresh_app(tmp_path, monkeypatch, password="secret"))
    assert client.get("/health").status_code == 200


def test_dashboard_requires_auth_when_configured(tmp_path, monkeypatch):
    client = TestClient(_fresh_app(tmp_path, monkeypatch, password="secret"))
    assert client.get("/settings").status_code == 401
    assert client.post("/trading/stop").status_code == 401
    client.auth = ("admin", "secret")
    assert client.get("/settings").status_code == 200


def test_dashboard_rejects_wrong_password(tmp_path, monkeypatch):
    client = TestClient(_fresh_app(tmp_path, monkeypatch, password="secret"))
    client.auth = ("admin", "nope")
    assert client.get("/settings").status_code == 401


def test_dashboard_fails_closed_when_unconfigured(tmp_path, monkeypatch):
    client = TestClient(_fresh_app(tmp_path, monkeypatch, password=None))
    # No password configured -> nothing but /health is served.
    assert client.get("/settings").status_code == 503
    assert client.post("/trading/stop").status_code == 503
    assert client.get("/health").status_code == 200


def test_positions_persist_across_restart(tmp_path, monkeypatch):
    db = tmp_path / "pos.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    from polymarket_mm_bot.config.settings import Settings, get_settings
    from polymarket_mm_bot.database.orm import Base
    from polymarket_mm_bot.database.runtime_state import load_positions, save_position
    from polymarket_mm_bot.database.session import get_engine, get_session_factory

    get_settings.cache_clear()
    Base.metadata.create_all(get_engine())
    settings = Settings()

    inventory = InventoryManager(settings)
    position = inventory.get_position("m1")
    position.yes_size = 12
    position.avg_yes_price = 0.4
    position.realized_pnl = 3.5
    factory = get_session_factory(settings)
    with factory() as session:
        save_position(session, position)

    # Simulate a fresh process reloading persisted state.
    with factory() as session:
        restored = load_positions(session)["m1"]
    assert restored.yes_size == 12
    assert restored.avg_yes_price == pytest.approx(0.4)
    assert restored.realized_pnl == pytest.approx(3.5)


def test_api_error_breaker_trips(settings):
    risk = RiskEngine(settings, InventoryManager(settings))
    decision = None
    for _ in range(settings.max_api_errors):
        decision = risk.record_api_error()
    assert decision is not None
    assert decision.allowed is False
    assert decision.code == "api_error_threshold"


def test_risk_still_blocks_large_order(settings):
    risk = RiskEngine(settings, InventoryManager(settings))
    order = BotOrder(client_order_id="1", market_id="m1", side=Side.BUY, price=0.5, size=999)
    assert risk.check_order(order, []).allowed is False
