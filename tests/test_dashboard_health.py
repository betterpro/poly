from fastapi.testclient import TestClient

from polymarket_mm_bot.dashboard.app import create_app


def test_health_prefers_trading_control_over_stale_snapshot(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    from polymarket_mm_bot.config.settings import get_settings
    from polymarket_mm_bot.database.orm import Base
    from polymarket_mm_bot.database.session import get_engine

    get_settings.cache_clear()
    monkeypatch.setattr("polymarket_mm_bot.dashboard.app.ensure_schema", lambda: None)
    monkeypatch.setattr(
        "polymarket_mm_bot.dashboard.app.get_cached_snapshot",
        lambda: {
            "trading_enabled": False,
            "bot_status": "trading_paused",
            "mode_warning": "paper",
            "allowed_categories": [],
        },
    )
    Base.metadata.create_all(get_engine())
    client = TestClient(create_app())

    assert client.post("/trading/resume").status_code == 200
    health = client.get("/health").json()

    assert health["trading_enabled"] is True
    assert health["bot_trading_enabled"] is False
    assert health["status"] == "trading_paused"
