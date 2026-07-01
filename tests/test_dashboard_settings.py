from fastapi.testclient import TestClient

from polymarket_mm_bot.config.runtime_settings import EditableBotSettings
from polymarket_mm_bot.dashboard.app import create_app


def test_settings_round_trip(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    from polymarket_mm_bot.config.settings import get_settings
    from polymarket_mm_bot.database.orm import Base
    from polymarket_mm_bot.database.session import get_engine

    get_settings.cache_clear()
    monkeypatch.setattr("polymarket_mm_bot.dashboard.app.ensure_schema", lambda: None)
    Base.metadata.create_all(get_engine())
    client = TestClient(create_app())
    current = client.get("/settings").json()
    assert current["paper_trading"] is True
    updated = {**current, "order_size": 15, "target_spread": 0.03, "allowed_categories": ["sports", "crypto"]}
    response = client.put("/settings", json=updated)
    assert response.status_code == 200
    body = response.json()
    assert body["order_size"] == 15
    assert body["allowed_categories"] == ["sports", "crypto"]
    assert EditableBotSettings.model_validate(body).order_size == 15
