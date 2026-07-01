def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


MARKET_CATEGORIES: tuple[str, ...] = (
    "sports",
    "crypto",
    "finance",
    "politics",
    "economics",
    "culture",
    "weather",
    "mentions",
    "tech",
    "geopolitics",
    "macro",
)

DEFAULT_ALLOWED_CATEGORIES: tuple[str, ...] = (
    "sports",
    "crypto",
    "macro",
    "politics",
    "economics",
    "finance",
)

# Gamma event tag slugs that map to each dashboard category.
CATEGORY_TAG_ALIASES: dict[str, frozenset[str]] = {
    "sports": frozenset(
        {
            "sports",
            "soccer",
            "nba",
            "nfl",
            "mlb",
            "nhl",
            "tennis",
            "fifa-world-cup",
            "football",
            "esports",
            "world-cup",
            "f1",
            "golf",
            "ufc",
            "cricket",
            "basketball",
            "baseball",
            "hockey",
        }
    ),
    "crypto": frozenset({"crypto", "bitcoin", "ethereum", "solana", "defi"}),
    "finance": frozenset({"finance", "business", "ipos", "stocks", "economy"}),
    "politics": frozenset({"politics", "elections", "trump", "biden"}),
    "economics": frozenset({"economics", "economy", "fed", "macro"}),
    "culture": frozenset({"culture", "pop-culture", "entertainment", "music", "movies"}),
    "weather": frozenset({"weather", "climate"}),
    "mentions": frozenset({"mentions"}),
    "tech": frozenset({"tech", "ai", "science"}),
    "geopolitics": frozenset({"geopolitics", "world", "ukraine", "israel"}),
    "macro": frozenset({"macro", "economics", "economy", "fed"}),
}


def normalize_category_list(value: list[str] | str | None) -> list[str]:
    if value is None:
        return list(DEFAULT_ALLOWED_CATEGORIES)
    items = [part.strip() for part in value.split(",")] if isinstance(value, str) else list(value)
    known = {category.lower() for category in MARKET_CATEGORIES}
    normalized: list[str] = []
    for item in items:
        category = str(item).strip().lower()
        if category in known and category not in normalized:
            normalized.append(category)
    return normalized or list(DEFAULT_ALLOWED_CATEGORIES)


def event_tag_slugs(event: dict | None) -> set[str]:
    slugs: set[str] = set()
    for tag in (event or {}).get("tags") or []:
        if isinstance(tag, str):
            slugs.add(tag.strip().lower())
        elif isinstance(tag, dict) and tag.get("slug"):
            slugs.add(str(tag["slug"]).strip().lower())
    return slugs


def category_aliases(category: str) -> frozenset[str]:
    normalized = category.strip().lower()
    return CATEGORY_TAG_ALIASES.get(normalized, frozenset({normalized}))


def event_belongs_to_category(event: dict, category: str) -> bool:
    return bool(event_tag_slugs(event) & category_aliases(category))


def market_category_slugs(category: str | None, metadata: dict | None = None) -> set[str]:
    slugs: set[str] = set()
    if category:
        slugs.add(category.strip().lower())
    data = metadata or {}
    slugs.update(event_tag_slugs(data.get("event") if isinstance(data.get("event"), dict) else None))
    for tag in data.get("tags") or []:
        if isinstance(tag, str):
            slugs.add(tag.strip().lower())
        elif isinstance(tag, dict) and tag.get("slug"):
            slugs.add(str(tag["slug"]).strip().lower())
    for event in data.get("events") or []:
        if isinstance(event, dict):
            slugs.update(event_tag_slugs(event))
    return slugs


def market_matches_categories(
    category: str | None,
    metadata: dict | None,
    allowed_categories: set[str] | frozenset[str],
) -> bool:
    slugs = market_category_slugs(category, metadata)
    for allowed in allowed_categories:
        if slugs & category_aliases(allowed):
            return True
    return False


def market_dict_matches_categories(market: dict, allowed_categories: set[str] | frozenset[str]) -> bool:
    metadata = market.get("metadata") if isinstance(market.get("metadata"), dict) else market
    event = metadata.get("event") if isinstance(metadata, dict) else None
    if isinstance(event, dict) and event_tag_slugs(event):
        return market_matches_categories(None, metadata, allowed_categories)
    return market_matches_categories(market.get("category"), metadata, allowed_categories)


def round_to_tick(value: float, tick: float) -> float:
    return round(round(value / tick) * tick, 6)


CATEGORY_FEE_RATES: dict[str, float] = {
    "crypto": 0.07,
    "sports": 0.03,
    "finance": 0.04,
    "politics": 0.04,
    "economics": 0.05,
    "culture": 0.05,
    "weather": 0.05,
    "mentions": 0.04,
    "tech": 0.04,
    "geopolitics": 0.0,
}

DEFAULT_FEE_RATE = 0.05


def fee_rate_for_category(category: str | None) -> float:
    if not category:
        return DEFAULT_FEE_RATE
    return CATEGORY_FEE_RATES.get(category.strip().lower(), DEFAULT_FEE_RATE)


def estimate_taker_fee(size: float, price: float | None, category: str | None) -> float:
    if price is None or price <= 0 or price >= 1 or size <= 0:
        return 0.0
    rate = fee_rate_for_category(category)
    if rate <= 0:
        return 0.0
    return size * rate * price * (1.0 - price)


def maker_fee() -> float:
    return 0.0
