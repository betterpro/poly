"""Dependency-free TOTP (RFC 6238) for confirming the paper -> live switch.

Implemented against the stdlib so the money-gating control adds no third-party
supply-chain surface. Compatible with Google Authenticator / Authy / 1Password
(SHA1, 6 digits, 30s period).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

_PERIOD = 30
_DIGITS = 6


def _decode_secret(secret: str) -> bytes:
    cleaned = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(cleaned) % 8) % 8)
    return base64.b32decode(cleaned + padding, casefold=True)


def _hotp(key: bytes, counter: int) -> str:
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % (10**_DIGITS)).zfill(_DIGITS)


def matched_counter(
    secret: str | None,
    code: str | None,
    *,
    valid_window: int = 1,
    now: float | None = None,
) -> int | None:
    """Return the time-counter a valid code matched, or None if invalid.

    The counter lets callers reject replays of an already-used code.
    """
    if not secret or not code:
        return None
    code = code.strip()
    if not code.isdigit() or len(code) != _DIGITS:
        return None
    try:
        key = _decode_secret(secret)
    except (binascii.Error, ValueError):
        return None
    reference = int((now if now is not None else time.time()) // _PERIOD)
    for drift in range(-valid_window, valid_window + 1):
        counter = reference + drift
        if hmac.compare_digest(_hotp(key, counter), code):
            return counter
    return None


def verify(secret: str | None, code: str | None, **kwargs) -> bool:
    return matched_counter(secret, code, **kwargs) is not None


def generate_secret() -> str:
    """Generate a fresh base32 secret for authenticator enrollment."""
    return base64.b32encode(secrets.token_bytes(20)).decode("utf-8").rstrip("=")


def provisioning_uri(secret: str, account_name: str, issuer: str = "polymarket-mm-bot") -> str:
    """Build an otpauth:// URI to render as a QR code during enrollment."""
    label = quote(f"{issuer}:{account_name}")
    return (
        f"otpauth://totp/{label}"
        f"?secret={secret}&issuer={quote(issuer)}&algorithm=SHA1&digits={_DIGITS}&period={_PERIOD}"
    )
