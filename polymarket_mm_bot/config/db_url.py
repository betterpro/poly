def normalize_database_url(url: str) -> str:
    cleaned = url.strip().strip('"').strip("'")
    if cleaned.startswith("postgresql://"):
        cleaned = "postgresql+psycopg://" + cleaned.removeprefix("postgresql://")
    if "supabase.co" in cleaned and "sslmode=" not in cleaned:
        separator = "&" if "?" in cleaned else "?"
        cleaned = f"{cleaned}{separator}sslmode=require"
    if cleaned.startswith("postgresql") and "connect_timeout=" not in cleaned:
        separator = "&" if "?" in cleaned else "?"
        cleaned = f"{cleaned}{separator}connect_timeout=5"
    return cleaned
