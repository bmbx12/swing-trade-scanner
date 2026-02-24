"""Core screening pipeline for swing trade candidates."""
import time
from datetime import datetime
from fmp_client import FMPClient
from stock_universe import get_stocks_by_sector
from scoring import (
    calculate_ath,
    calculate_pct_below_ath,
    calculate_upside,
    passes_filters,
    score_stock,
    rank_stocks,
)

# FMP free tier = 250 API calls/day
# Budget: 1 (sector perf) + ~60 (quotes) + ~20 (historical) = ~81 calls per scan
MAX_SECTORS = 3
MAX_CANDIDATES_PER_SECTOR = 20


class Scanner:
    def __init__(self, client: FMPClient, config: dict = None):
        self.client = client
        self.config = config or {
            "market_cap_min": 1_000_000_000,
            "volume_min": 500_000,
            "ath_min": 15.0,
            "ath_max": 50.0,
            "top_n": 15,
        }
        self._api_calls = 0

    def _track_call(self):
        """Track API call count for budget awareness."""
        self._api_calls += 1

    def get_winning_sectors(self) -> list[dict]:
        """Step 1: Get sectors outperforming the market (1 API call)."""
        self._track_call()
        sectors = self.client.get_sector_performance()
        winning = [
            s for s in sectors
            if float(s.get("changesPercentage", "0").replace("%", "")) > 0
        ]
        winning.sort(
            key=lambda s: float(s["changesPercentage"].replace("%", "")),
            reverse=True,
        )
        # Limit to top sectors to conserve API budget
        return winning[:MAX_SECTORS]

    def get_candidates(self, sectors: list[dict]) -> list[dict]:
        """Step 2: Get stocks from embedded universe in winning sectors (0 API calls)."""
        candidates = []
        for sector_data in sectors:
            fmp_sector_name = sector_data["sector"]
            sector_perf = float(
                sector_data["changesPercentage"].replace("%", "")
            )
            stocks = get_stocks_by_sector(fmp_sector_name)
            # Limit per sector to stay within API budget
            for stock in stocks[:MAX_CANDIDATES_PER_SECTOR]:
                candidates.append({
                    "symbol": stock["symbol"],
                    "name": stock["name"],
                    "sector": fmp_sector_name,
                    "sector_performance": sector_perf,
                })
        return candidates

    def quick_filter(self, candidate: dict) -> dict | None:
        """Step 3a: Quick filter using quote data (1 API call per stock).

        Returns enriched candidate if it passes initial screen, None otherwise.
        Uses 52-week high as ATH proxy to avoid historical API calls for
        stocks that clearly don't meet criteria.
        """
        symbol = candidate["symbol"]
        self._track_call()
        quote = self.client.get_quote(symbol)

        price = quote.get("price", 0)
        year_high = quote.get("yearHigh", 0)

        if price == 0 or year_high == 0:
            return None

        # Quick check: % below 52-week high as ATH proxy
        pct_below_52w = ((year_high - price) / year_high) * 100

        # Only fetch historical if stock is roughly in our ATH range
        # Use wider bounds (10%-60%) since 52-week high != ATH
        if pct_below_52w < (self.config["ath_min"] - 5) or pct_below_52w > (self.config["ath_max"] + 10):
            return None

        return {
            **candidate,
            "price": price,
            "name": quote.get("name", candidate.get("name", "")),
            "yearHigh": year_high,
            "yearLow": quote.get("yearLow", 0),
            "volume": quote.get("volume", 0),
            "avgVolume": quote.get("averageVolume", 0),
        }

    def enrich_candidate(self, candidate: dict) -> dict | None:
        """Step 3b: Add historical ATH data and score (1 API call per stock)."""
        symbol = candidate["symbol"]

        self._track_call()
        historical = self.client.get_historical_prices(symbol, timeseries=365)
        hist_data = historical.get("historical", [])
        ath = calculate_ath(hist_data)

        if ath is None:
            # Fallback to 52-week high if no historical data
            ath = candidate.get("yearHigh", 0)
        if ath == 0:
            return None

        price = candidate["price"]
        pct_below = calculate_pct_below_ath(price, ath)
        target = ath
        upside = calculate_upside(price, target)

        enriched = {
            "symbol": symbol,
            "name": candidate.get("name", ""),
            "sector": candidate.get("sector", ""),
            "sector_performance": candidate.get("sector_performance", 0),
            "price": price,
            "yearHigh": candidate.get("yearHigh", 0),
            "yearLow": candidate.get("yearLow", 0),
            "volume": candidate.get("volume", 0),
            "avgVolume": candidate.get("avgVolume", 0),
            "ath": ath,
            "pct_below_ath": round(pct_below, 1),
            "target_price": round(target, 2),
            "upside_pct": round(upside, 1),
        }

        enriched["score"] = score_stock(enriched)
        return enriched

    def run_scan(self, progress_callback=None) -> dict:
        """Run the full screening pipeline.

        Pipeline:
        1. Get sector performance -> find top 3 winning sectors (1 API call)
        2. Get candidates from S&P 500 universe in winning sectors (0 API calls)
        3a. Quick filter: get quote, check 52-week range (~60 API calls)
        3b. Deep enrich: get historical prices for ATH, score (~20 API calls)
        4. Rank and return top N

        Total budget: ~81 API calls per scan (well within 250/day free limit)
        """
        start_time = time.time()
        self._api_calls = 0

        # Step 1: Sector performance
        if progress_callback:
            progress_callback("Analyzing sector performance...")
        winning_sectors = self.get_winning_sectors()

        # Step 2: Get candidates from universe
        if progress_callback:
            progress_callback(
                f"Found {len(winning_sectors)} top sectors, loading candidates..."
            )
        candidates = self.get_candidates(winning_sectors)

        # Step 3a: Quick filter with quotes
        quick_passed = []
        total = len(candidates)
        for i, candidate in enumerate(candidates):
            if progress_callback and i % 10 == 0:
                progress_callback(
                    f"Screening {i+1}/{total}: {candidate['symbol']}..."
                )
            try:
                result = self.quick_filter(candidate)
                if result:
                    quick_passed.append(result)
            except Exception:
                continue

        # Step 3b: Deep enrich with historical data
        enriched = []
        for i, candidate in enumerate(quick_passed):
            if progress_callback:
                progress_callback(
                    f"Deep analysis {i+1}/{len(quick_passed)}: {candidate['symbol']}..."
                )
            try:
                result = self.enrich_candidate(candidate)
                if result and passes_filters(
                    result,
                    ath_min=self.config["ath_min"],
                    ath_max=self.config["ath_max"],
                ):
                    enriched.append(result)
            except Exception:
                continue

        # Step 4: Rank
        if progress_callback:
            progress_callback("Ranking candidates...")
        ranked = rank_stocks(enriched, limit=self.config["top_n"])

        elapsed = round(time.time() - start_time, 1)

        return {
            "stocks": ranked,
            "scan_metadata": {
                "timestamp": datetime.now().isoformat(),
                "winning_sectors": [
                    {
                        "name": s["sector"],
                        "performance": float(
                            s["changesPercentage"].replace("%", "")
                        ),
                    }
                    for s in winning_sectors
                ],
                "total_candidates": len(candidates),
                "quick_filtered": len(quick_passed),
                "passed_filters": len(enriched),
                "api_calls_used": self._api_calls,
                "elapsed_seconds": elapsed,
            },
        }
