"""Generate a TOTP secret for the paper -> live dashboard switch.

Usage:
    python -m scripts.setup_live_totp [account_name]

Copy the printed secret into an authenticator app (Google Authenticator, Authy,
1Password, ...) and set it as LIVE_TOTP_SECRET in the server environment. The
otpauth:// URI can be pasted into a QR generator for easy enrollment.
"""

from __future__ import annotations

import sys

from polymarket_mm_bot.security import totp


def main() -> None:
    account = sys.argv[1] if len(sys.argv) > 1 else "operator"
    secret = totp.generate_secret()
    uri = totp.provisioning_uri(secret, account)
    print("Add this to the server environment:")
    print(f"  LIVE_TOTP_SECRET={secret}")
    print()
    print("Enroll in your authenticator app with either the secret above or this URI:")
    print(f"  {uri}")
    print()
    print("Keep the secret private. Anyone with it can approve switching to live trading.")


if __name__ == "__main__":
    main()
