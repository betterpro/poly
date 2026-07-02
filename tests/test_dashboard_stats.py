from fastapi.testclient import TestClient

from polymarket_mm_bot.dashboard import app as dashboard_app


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
    }
    monkeypatch.setattr(dashboard_app, "_status", lambda: snapshot)
    monkeypatch.setattr(
        dashboard_app,
        "load_daily_pnl_tracking",
        lambda: {"baseline": 1.0, "reset_at": "2026-07-01T00:00:00+00:00"},
    )
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    from polymarket_mm_bot.config.settings import get_settings

    get_settings.cache_clear()
    client = TestClient(dashboard_app.create_app())
    client.auth = ("admin", "secret")

    body = client.get("/pnl").json()
    assert body["realized_pnl"] == 2.0
    assert body["unrealized_pnl"] == -0.5
    assert body["total_pnl"] == 1.5
    assert body["daily_pnl"] == 0.5
