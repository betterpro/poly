from dotenv import dotenv_values
import subprocess

cfg = dotenv_values(".env")
secrets = {
    "DIGITALOCEAN_ACCESS_TOKEN": cfg.get("DIGITAL_OCEAN_API_KEY"),
    "DATABASE_URL": (cfg.get("DATABASE_URL") or "").strip('"'),
    "POLYMARKET_API_KEY": cfg.get("POLYMARKET_API_KEY") or "",
    "POLYMARKET_API_SECRET": (cfg.get("POLYMARKET_API_SECRET") or "").strip('"'),
    "POLYMARKET_API_PASSPHRASE": cfg.get("POLYMARKET_API_PASSPHRASE") or "",
    "POLYMARKET_PRIVATE_KEY": cfg.get("POLYMARKET_PRIVATE_KEY") or "",
    "POLYMARKET_FUNDER_ADDRESS": cfg.get("POLYMARKET_FUNDER_ADDRESS") or "",
}
for name, value in secrets.items():
    if not value:
        print(f"skip {name} (empty)")
        continue
    subprocess.run(["gh", "secret", "set", name, "--body", value], check=True)
    print(f"set {name}")
