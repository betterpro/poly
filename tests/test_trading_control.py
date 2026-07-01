from polymarket_mm_bot.dashboard.trading_control import (
    is_trading_enabled,
    load_trading_control,
    resume_trading,
    stop_trading,
)


def test_trading_enabled_by_default(settings, monkeypatch):
    saved = {}

    def fake_load(session=None):
        return dict(saved) if saved else {"enabled": True}

    def fake_save(control, session=None):
        saved.clear()
        saved.update(control)
        return control

    monkeypatch.setattr("polymarket_mm_bot.dashboard.trading_control.load_trading_control", fake_load)
    monkeypatch.setattr("polymarket_mm_bot.dashboard.trading_control.save_trading_control", fake_save)

    assert is_trading_enabled() is True
    control = stop_trading()
    assert control["enabled"] is False
    assert is_trading_enabled() is False
    control = resume_trading()
    assert control["enabled"] is True
    assert is_trading_enabled() is True


def test_load_trading_control_defaults_when_missing(settings, monkeypatch):
    monkeypatch.setattr(
        "polymarket_mm_bot.dashboard.trading_control._get_row",
        lambda session: type("Row", (), {"config_json": {}})(),
    )
    assert load_trading_control(object()) == {"enabled": True}
