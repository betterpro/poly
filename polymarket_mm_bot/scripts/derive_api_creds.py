"""Derive Polymarket L2 API credentials from POLYMARKET_PRIVATE_KEY in .env."""

from pathlib import Path

from dotenv import dotenv_values
from py_clob_client_v2 import ClobClient


def main() -> None:
    env_path = Path(".env")
    cfg = dotenv_values(env_path)
    private_key = cfg.get("POLYMARKET_PRIVATE_KEY")
    if not private_key:
        raise SystemExit("Set POLYMARKET_PRIVATE_KEY in .env first.")

    client = ClobClient("https://clob.polymarket.com", key=private_key, chain_id=137)
    creds = client.create_or_derive_api_key()

    print("Add these to your .env:\n")
    print(f"POLYMARKET_API_KEY={creds.api_key}")
    print(f"POLYMARKET_API_SECRET={creds.api_secret}")
    print(f"POLYMARKET_API_PASSPHRASE={creds.api_passphrase}")


if __name__ == "__main__":
    main()
