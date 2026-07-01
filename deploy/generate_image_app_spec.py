from pathlib import Path

from dotenv import dotenv_values

from polymarket_mm_bot.config.db_url import normalize_database_url

cfg = dotenv_values(".env")
template = Path("deploy/app.image.template.yaml").read_text(encoding="utf-8")
db_url = normalize_database_url(cfg.get("DATABASE_URL") or "")
replacements = {
    "__DATABASE_URL__": db_url,
    "__POLYMARKET_API_KEY__": cfg.get("POLYMARKET_API_KEY") or "",
    "__POLYMARKET_API_SECRET__": (cfg.get("POLYMARKET_API_SECRET") or "").strip('"'),
    "__POLYMARKET_API_PASSPHRASE__": cfg.get("POLYMARKET_API_PASSPHRASE") or "",
    "__POLYMARKET_PRIVATE_KEY__": cfg.get("POLYMARKET_PRIVATE_KEY") or "",
    "__POLYMARKET_FUNDER_ADDRESS__": cfg.get("POLYMARKET_FUNDER_ADDRESS") or "",
}
for key, value in replacements.items():
    template = template.replace(key, value)
Path("deploy/app-spec.generated.yaml").write_text(template, encoding="utf-8")
print("Generated deploy/app-spec.generated.yaml")
