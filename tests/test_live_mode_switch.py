"""Tests for the TOTP-gated paper -> live mode switch."""

from __future__ import annotations

import pytest

from polymarket_mm_bot.security import totp


def _valid_code(secret: str, now: float) -> str:
    import base64
    import hashlib
    import hmac
    import struct

    key = base64.b32decode(secret + "=" * ((8 - len(secret) % 8) % 8), casefold=True)
    counter = int(now // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % 1_000_000).zfill(6)


def test_totp_roundtrip():
    secret = totp.generate_secret()
    now = 1_000_000.0
    code = _valid_code(secret, now)
    assert totp.verify(secret, code, now=now)
    assert not totp.verify(secret, "000000", now=now)
    assert not totp.verify(secret, "abc", now=now)
    assert not totp.verify(secret, "", now=now)
    assert not totp.verify(None, code, now=now)


def test_totp_counter_advances():
    secret = totp.generate_secret()
    c1 = totp.matched_counter(secret, _valid_code(secret, 1_000_000.0), now=1_000_000.0)
    c2 = totp.matched_counter(secret, _valid_code(secret, 1_000_090.0), now=1_000_090.0)
    assert c1 is not None and c2 is not None
    assert c2 > c1


def _prepare_db(tmp_path, monkeypatch, **env):
    db = tmp_path / "mode.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    from polymarket_mm_bot.config.runtime_settings import clear_runtime_settings_cache
    from polymarket_mm_bot.config.settings import get_settings
    from polymarket_mm_bot.database.orm import Base
    from polymarket_mm_bot.database.session import get_engine

    get_settings.cache_clear()
    clear_runtime_settings_cache()
    Base.metadata.create_all(get_engine())


def test_switch_to_live_requires_prerequisites(tmp_path, monkeypatch):
    _prepare_db(tmp_path, monkeypatch)  # nothing configured
    from polymarket_mm_bot.dashboard.mode_control import switch_to_live

    with pytest.raises(ValueError, match="TOTP"):
        switch_to_live("123456")


def test_switch_to_live_rejects_bad_code(tmp_path, monkeypatch):
    secret = totp.generate_secret()
    _prepare_db(
        tmp_path,
        monkeypatch,
        LIVE_TOTP_SECRET=secret,
        LIVE_TRADING_CONFIRMED="true",
        POLYMARKET_PRIVATE_KEY="0xkey",
        POLYMARKET_FUNDER_ADDRESS="0xwallet",
    )
    from polymarket_mm_bot.dashboard.mode_control import get_mode_state, switch_to_live

    assert get_mode_state()["mode"] == "paper"
    with pytest.raises(ValueError, match="Invalid authenticator code"):
        switch_to_live("000000")
    # Still paper after a failed attempt.
    assert get_mode_state()["mode"] == "paper"


def test_switch_to_live_and_back(tmp_path, monkeypatch):
    import time

    secret = totp.generate_secret()
    _prepare_db(
        tmp_path,
        monkeypatch,
        LIVE_TOTP_SECRET=secret,
        LIVE_TRADING_CONFIRMED="true",
        POLYMARKET_PRIVATE_KEY="0xkey",
        POLYMARKET_FUNDER_ADDRESS="0xwallet",
    )
    from polymarket_mm_bot.dashboard.mode_control import get_mode_state, switch_to_live, switch_to_paper

    code = _valid_code(secret, time.time())
    state = switch_to_live(code)
    assert state["mode"] == "live"
    assert state["paper_trading"] is False
    assert state["prerequisites"]["execution_implemented"] is True

    # Replaying the same code is rejected.
    with pytest.raises(ValueError, match="already used"):
        switch_to_live(code)

    # Returning to paper needs no code.
    back = switch_to_paper()
    assert back["mode"] == "paper"
    assert get_mode_state()["mode"] == "paper"


def test_plain_settings_save_cannot_flip_mode(tmp_path, monkeypatch):
    import time

    secret = totp.generate_secret()
    _prepare_db(
        tmp_path,
        monkeypatch,
        LIVE_TOTP_SECRET=secret,
        LIVE_TRADING_CONFIRMED="true",
        POLYMARKET_PRIVATE_KEY="0xkey",
        POLYMARKET_FUNDER_ADDRESS="0xwallet",
    )
    from polymarket_mm_bot.config.runtime_settings import get_editable_settings, save_editable_settings
    from polymarket_mm_bot.dashboard.mode_control import get_mode_state, switch_to_live

    # Go live via the gated path.
    switch_to_live(_valid_code(secret, time.time()))
    assert get_mode_state()["mode"] == "live"

    # A malicious/plain settings save trying to force paper mode must not change mode.
    editable = get_editable_settings()
    editable.paper_trading = True
    editable.run_mode = "paper"
    editable.order_size = 7
    save_editable_settings(editable)

    assert get_mode_state()["mode"] == "live"  # mode preserved
    assert get_editable_settings().order_size == 7  # other fields still saved
