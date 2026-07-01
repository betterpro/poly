from datetime import UTC, datetime
from unittest.mock import patch

from polymarket_mm_bot.dashboard.pnl_baseline import reset_daily_pnl_baseline, resolve_daily_pnl


def test_resolve_daily_pnl_uses_saved_baseline(settings, monkeypatch):
    saved = {}

    def fake_load(session=None):
        return dict(saved) if saved else None

    def fake_save(tracking, session=None):
        saved.clear()
        saved.update(tracking)
        return tracking

    monkeypatch.setattr("polymarket_mm_bot.dashboard.pnl_baseline.load_daily_pnl_tracking", fake_load)
    monkeypatch.setattr("polymarket_mm_bot.dashboard.pnl_baseline.save_daily_pnl_tracking", fake_save)

    morning = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    with patch("polymarket_mm_bot.dashboard.pnl_baseline.datetime") as mock_datetime:
        mock_datetime.now.return_value = morning
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        baseline, daily, _ = resolve_daily_pnl(0.0)
        assert baseline == 0.0
        assert daily == 0.0

        baseline, daily, _ = resolve_daily_pnl(-0.2)
        assert baseline == 0.0
        assert daily == -0.2

    evening = datetime(2026, 7, 1, 22, 0, tzinfo=UTC)
    with patch("polymarket_mm_bot.dashboard.pnl_baseline.datetime") as mock_datetime:
        mock_datetime.now.return_value = evening
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        baseline, daily, _ = resolve_daily_pnl(-0.5)
        assert baseline == 0.0
        assert daily == -0.5


def test_reset_daily_pnl_baseline(settings, monkeypatch):
    saved = {}

    def fake_load(session=None):
        return dict(saved) if saved else None

    def fake_save(tracking, session=None):
        saved.clear()
        saved.update(tracking)
        return tracking

    monkeypatch.setattr("polymarket_mm_bot.dashboard.pnl_baseline.load_daily_pnl_tracking", fake_load)
    monkeypatch.setattr("polymarket_mm_bot.dashboard.pnl_baseline.save_daily_pnl_tracking", fake_save)

    fixed = datetime(2026, 7, 1, 15, 0, tzinfo=UTC)
    with patch("polymarket_mm_bot.dashboard.pnl_baseline.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        result = reset_daily_pnl_baseline(-0.2)
        assert result["daily_pnl"] == 0.0
        assert result["baseline"] == -0.2
        assert saved["reset_by"] == "manual"

        baseline, daily, _ = resolve_daily_pnl(-0.5)
        assert baseline == -0.2
        assert daily == -0.3
