"""Pure scoring and filtering functions for swing trade candidates."""


def calculate_ath(historical: list[dict]) -> float | None:
    """Calculate all-time high from historical price data."""
    if not historical:
        return None
    return max(entry["high"] for entry in historical)


def calculate_pct_below_ath(current_price: float, ath: float) -> float:
    """Calculate percentage below all-time high."""
    if ath == 0:
        return 0.0
    return ((ath - current_price) / ath) * 100


def calculate_upside(current_price: float, target_price: float) -> float:
    """Calculate potential upside percentage from current to target."""
    if current_price == 0:
        return 0.0
    return ((target_price - current_price) / current_price) * 100


def passes_filters(
    stock: dict, ath_min: float = 15.0, ath_max: float = 50.0
) -> bool:
    """Check if a stock passes the swing trade filters."""
    pct_below = stock.get("pct_below_ath", 0)
    return ath_min <= pct_below <= ath_max


def score_stock(stock: dict) -> float:
    """
    Calculate composite conviction score (0-100).

    Weights:
    - Upside potential: 35%
    - Sector strength: 20%
    - Volume trend (current vs avg): 15%
    - Value positioning (price relative to 52-week range): 30%
    """
    # Upside score: 0-100 based on upside potential (cap at 100% upside)
    upside = min(stock.get("upside_pct", 0), 100)
    upside_score = upside

    # Sector score: normalize sector performance (-5 to +5 range typical)
    sector_perf = stock.get("sector_performance", 0)
    sector_score = max(0, min(100, (sector_perf + 5) * 10))

    # Volume trend: current volume vs average (>1 = accumulation signal)
    volume = stock.get("volume", 0)
    avg_volume = stock.get("avgVolume", 1)
    vol_ratio = volume / avg_volume if avg_volume > 0 else 1.0
    volume_score = max(0, min(100, vol_ratio * 50))

    # Value positioning: how close to 52-week low (closer = more value)
    price = stock.get("price", 0)
    year_low = stock.get("yearLow", 0)
    year_high = stock.get("yearHigh", 1)
    year_range = year_high - year_low
    if year_range > 0:
        value_score = ((year_high - price) / year_range) * 100
    else:
        value_score = 50

    score = (
        upside_score * 0.35
        + sector_score * 0.20
        + volume_score * 0.15
        + value_score * 0.30
    )

    return round(max(0, min(100, score)), 1)


def rank_stocks(stocks: list[dict], limit: int = 15) -> list[dict]:
    """Sort stocks by score descending and add rank."""
    sorted_stocks = sorted(stocks, key=lambda s: s["score"], reverse=True)
    for i, stock in enumerate(sorted_stocks[:limit]):
        stock["rank"] = i + 1
    return sorted_stocks[:limit]
