from fastapi.testclient import TestClient

from polymarket_mm_bot.config.runtime_settings import EditableBotSettings
from polymarket_mm_bot.dashboard.app import create_app


def test_settings_round_trip(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    from polymarket_mm_bot.config.settings import get_settings
    from polymarket_mm_bot.database.orm import Base
    from polymarket_mm_bot.database.session import get_engine

    get_settings.cache_clear()
    monkeypatch.setattr("polymarket_mm_bot.dashboard.app.ensure_schema", lambda: None)
    Base.metadata.create_all(get_engine())
    client = TestClient(create_app())
    client.auth = ("admin", "secret")
    current = client.get("/settings").json()
    assert current["paper_trading"] is True
    updated = {
        **current,
        "order_size": 15,
        "target_spread": 0.03,
        "per_market_stop_loss": 1.5,
        "optimizer_auto_enabled": True,
        "optimizer_scale_multiplier": 1.7,
        "allowed_categories": ["sports", "crypto"],
    }
    response = client.put("/settings", json=updated)
    assert response.status_code == 200
    body = response.json()
    assert body["order_size"] == 15
    assert body["per_market_stop_loss"] == 1.5
    assert body["optimizer_scale_multiplier"] == 1.7
    assert body["allowed_categories"] == ["sports", "crypto"]
    assert EditableBotSettings.model_validate(body).order_size == 15


def test_clean_database_clears_runtime_state_and_pauses_trading(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    from polymarket_mm_bot.config.runtime_settings import clear_runtime_settings_cache
    from polymarket_mm_bot.config.settings import get_settings
    from polymarket_mm_bot.database.orm import Base, BotConfigRow, BotOrderRow, MarketRow, PositionRow, RiskEventRow
    from polymarket_mm_bot.database.session import get_engine, get_session_factory

    get_settings.cache_clear()
    clear_runtime_settings_cache()
    monkeypatch.setattr("polymarket_mm_bot.dashboard.app.ensure_schema", lambda: None)
    Base.metadata.create_all(get_engine())
    with get_session_factory()() as session:
        session.add(
            BotConfigRow(
                id=1,
                config_json={"order_size": 15, "daily_pnl_tracking": {"baseline": -24.1}},
                status_json={"total_pnl": -24.1, "orders": [{"client_order_id": "paper-1"}]},
            )
        )
        session.add(
            BotOrderRow(
                client_order_id="paper-1",
                market_id="m1",
                side="buy",
                outcome="YES",
                price=0.5,
                size=10,
                filled_size=0,
                status="open",
            )
        )
        session.add(PositionRow(market_id="m1", yes_size=10, no_size=0, realized_pnl=-1, avg_yes_price=0.5, avg_no_price=0))
        session.add(RiskEventRow(market_id="m1", code="test", message="test", metadata_json={}))
        session.add(MarketRow(condition_id="m1", question="Will this clear?", metadata_json={}))
        session.commit()

    client = TestClient(create_app())
    client.auth = ("admin", "secret")
    response = client.post("/settings/clean-database")

    assert response.status_code == 200
    body = response.json()
    assert body["trading_enabled"] is False
    assert body["deleted"]["bot_orders"] == 1
    assert body["deleted"]["positions"] == 1
    assert body["deleted"]["risk_events"] == 1
    assert body["deleted"]["markets"] == 1
    with get_session_factory()() as session:
        row = session.get(BotConfigRow, 1)
        assert row is not None
        assert row.status_json == {}
        assert row.config_json["order_size"] == 15
        assert row.config_json["trading_control"]["enabled"] is False
        assert row.config_json["daily_pnl_tracking"]["baseline"] == 0
        assert row.config_json["daily_pnl_tracking"]["reset_by"] == "database_clean"
        assert session.query(BotOrderRow).count() == 0
        assert session.query(PositionRow).count() == 0
