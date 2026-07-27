from fastapi.testclient import TestClient

from polymarket_mm_bot.dashboard import app as dashboard_app
from polymarket_mm_bot.dashboard.pages import DASHBOARD_HTML


def test_dashboard_renders_strategy_profiles_section():
    assert "Strategy profiles" in DASHBOARD_HTML
    assert "/strategy-profiles" in DASHBOARD_HTML
    assert "Daily profit" in DASHBOARD_HTML
    assert "/pnl/daily" in DASHBOARD_HTML
    assert "Performance optimizer" in DASHBOARD_HTML
    assert "/performance/optimizer" in DASHBOARD_HTML


def test_fills_endpoint_returns_newest_first(monkeypatch):
    snapshot = {
        "recent_fills": [
            {"order_id": "a", "market_id": "m1", "side": "buy", "size": 4, "price": 0.5, "at": "2026-07-01T00:00:00+00:00"},
            {"order_id": "b", "market_id": "m1", "side": "sell", "size": 2, "price": 0.6, "at": "2026-07-01T00:01:00+00:00"},
        ]
    }
    monkeypatch.setattr(dashboard_app, "_status", lambda: snapshot)
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    from polymarket_mm_bot.config.settings import get_settings

    get_settings.cache_clear()
    client = TestClient(dashboard_app.create_app())
    client.auth = ("admin", "secret")

    fills = client.get("/fills").json()
    assert [f["order_id"] for f in fills] == ["b", "a"]  # newest first


def test_strategy_profiles_endpoint_returns_snapshot_profiles(monkeypatch):
    snapshot = {
        "strategy_profiles": [
            {
                "name": "active",
                "daily_pnl": 12.5,
                "target_daily_pnl": 100,
                "target_progress_pct": 12.5,
            }
        ]
    }
    monkeypatch.setattr(dashboard_app, "_status", lambda: snapshot)
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    from polymarket_mm_bot.config.settings import get_settings

    get_settings.cache_clear()
    client = TestClient(dashboard_app.create_app())
    client.auth = ("admin", "secret")

    profiles = client.get("/strategy-profiles").json()
    assert profiles[0]["name"] == "active"
    assert profiles[0]["target_progress_pct"] == 12.5


def test_dashboard_normalizes_order_and_position_metrics(monkeypatch):
    snapshot = {
        "orders": [
            {
                "client_order_id": "paper-1",
                "market_id": "m1",
                "side": "buy",
                "price": 0.5,
                "size": 10,
                "filled_size": 4,
                "status": "partially_filled",
            }
        ],
        "positions": [
            {
                "market_id": "m1",
                "yes_size": 10,
                "no_size": 2,
                "avg_yes_price": 0.4,
                "avg_no_price": 0.6,
                "realized_pnl": 1.0,
                "unrealized_pnl": 0.5,
            }
        ],
    }
    monkeypatch.setattr(dashboard_app, "_status", lambda: snapshot)
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    from polymarket_mm_bot.config.settings import get_settings

    get_settings.cache_clear()
    client = TestClient(dashboard_app.create_app())
    client.auth = ("admin", "secret")

    order = client.get("/orders").json()[0]
    assert order["remaining_size"] == 6
    assert order["notional"] == 5
    assert order["filled_notional"] == 2
    assert order["remaining_notional"] == 3

    position = client.get("/positions").json()[0]
    assert position["net_yes"] == 8
    assert position["gross_exposure"] == 5.2
    assert position["total_pnl"] == 1.5


def test_dashboard_pnl_reconciles_total_and_daily_baseline(monkeypatch):
    snapshot = {
        "realized_pnl": 2.0,
        "unrealized_pnl": -0.5,
        "total_pnl": 99.0,
        "daily_pnl": 99.0,
        "daily_pnl_reset_at": "2026-07-01T00:00:00+00:00",
        "positions": [
            {
                "market_id": "m1",
                "yes_size": 10,
                "no_size": 0,
                "avg_yes_price": 0.4,
                "avg_no_price": 0.0,
                "realized_pnl": 2.0,
                "unrealized_pnl": -0.5,
            }
        ],
        "orders": [
            {
                "client_order_id": "paper-1",
                "market_id": "m1",
                "side": "buy",
                "price": 0.5,
                "size": 10,
                "filled_size": 0,
                "status": "open",
            }
        ],
        "recent_fills": [
            {"order_id": "a", "market_id": "m1", "side": "buy", "size": 4, "price": 0.5, "value": 2.0},
            {"order_id": "b", "market_id": "m1", "side": "sell", "size": 2, "price": 0.6, "value": 1.2},
        ],
    }
    monkeypatch.setattr(dashboard_app, "_status", lambda: snapshot)
    monkeypatch.setattr(
        dashboard_app,
        "load_daily_pnl_tracking",
        lambda: {"baseline": 1.0, "reset_at": "2026-07-01T00:00:00+00:00"},
    )
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("STARTING_CAPITAL", "10000")
    from polymarket_mm_bot.config.settings import get_settings

    get_settings.cache_clear()
    client = TestClient(dashboard_app.create_app())
    client.auth = ("admin", "secret")

    body = client.get("/pnl").json()
    assert body["realized_pnl"] == 2.0
    assert body["unrealized_pnl"] == -0.5
    assert body["total_pnl"] == 1.5
    assert body["daily_pnl"] == 0.5
    assert body["profit"] == 2.0
    assert body["loss"] == 0.5
    assert body["position_credit"] == 4.0
    assert body["open_order_credit"] == 5.0
    assert body["capital_deployed"] == 9.0
    assert body["total_bought"] == 2.0
    assert body["total_sold"] == 1.2
    assert body["starting_capital"] == 10_000.0
    assert body["available_credit"] == 9992.5


def test_daily_pnl_endpoint_returns_history(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    db = tmp_path / "daily-endpoint.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    from polymarket_mm_bot.config.settings import get_settings
    from polymarket_mm_bot.database.orm import Base, PnlSnapshotRow
    from polymarket_mm_bot.database.session import get_engine, get_session_factory

    get_settings.cache_clear()
    monkeypatch.setattr("polymarket_mm_bot.dashboard.app.ensure_schema", lambda: None)
    Base.metadata.create_all(get_engine())
    with get_session_factory()() as session:
        session.add(PnlSnapshotRow(timestamp=datetime(2026, 7, 10, tzinfo=UTC), total_pnl=1, daily_pnl=0, unrealized_pnl=0, metadata_json={}))
        session.add(PnlSnapshotRow(timestamp=datetime(2026, 7, 11, tzinfo=UTC), total_pnl=3.5, daily_pnl=2.5, unrealized_pnl=1, metadata_json={}))
        session.commit()

    client = TestClient(dashboard_app.create_app())
    client.auth = ("admin", "secret")

    body = client.get("/pnl/daily").json()

    assert [row["date"] for row in body["days"]] == ["2026-07-10", "2026-07-11"]
    assert body["days"][1]["daily_pnl"] == 2.5


def test_optimizer_endpoint_returns_market_recommendations(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    db = tmp_path / "optimizer.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    from polymarket_mm_bot.config.settings import get_settings
    from polymarket_mm_bot.database.orm import Base, MarketRow, TradeRow
    from polymarket_mm_bot.database.session import get_engine, get_session_factory

    get_settings.cache_clear()
    monkeypatch.setattr("polymarket_mm_bot.dashboard.app.ensure_schema", lambda: None)
    Base.metadata.create_all(get_engine())
    with get_session_factory()() as session:
        session.add(MarketRow(condition_id="m1", question="Will this profit?", metadata_json={}))
        session.add_all(
            [
                TradeRow(order_id="b1", market_id="m1", token_id="yes", side="buy", price=0.4, size=10, timestamp=datetime(2026, 7, 18, 1, tzinfo=UTC)),
                TradeRow(order_id="s1", market_id="m1", token_id="yes", side="sell", price=0.5, size=5, timestamp=datetime(2026, 7, 18, 2, tzinfo=UTC)),
                TradeRow(order_id="s2", market_id="m1", token_id="yes", side="sell", price=0.52, size=5, timestamp=datetime(2026, 7, 18, 3, tzinfo=UTC)),
                TradeRow(order_id="b2", market_id="m1", token_id="yes", side="buy", price=0.41, size=1, timestamp=datetime(2026, 7, 18, 4, tzinfo=UTC)),
            ]
        )
        session.commit()

    client = TestClient(dashboard_app.create_app())
    client.auth = ("admin", "secret")

    body = client.get("/performance/optimizer").json()

    assert body["summary"]["fills"] == 4
    assert body["markets"][0]["market_id"] == "m1"
    assert body["markets"][0]["realized_pnl"] == 1.1
    assert body["markets"][0]["recommendation"] == "candidate_scale_up"


def test_optimizer_plan_endpoint_returns_last_decision(monkeypatch):
    snapshot = {
        "optimizer_plan": {
            "ran": True,
            "action": "scale_profitable_flow",
            "changed": {"order_size": {"before": 50, "after": 57.5}},
        }
    }
    monkeypatch.setattr(dashboard_app, "_status", lambda: snapshot)
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    from polymarket_mm_bot.config.settings import get_settings

    get_settings.cache_clear()
    client = TestClient(dashboard_app.create_app())
    client.auth = ("admin", "secret")

    body = client.get("/performance/optimizer/plan").json()

    assert body["enabled"] is True
    assert body["target_daily_pnl"] == 100.0
    assert body["last_decision"]["action"] == "scale_profitable_flow"
