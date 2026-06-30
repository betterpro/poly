def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def round_to_tick(value: float, tick: float) -> float:
    return round(round(value / tick) * tick, 6)
