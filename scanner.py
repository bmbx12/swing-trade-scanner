"""Core screening pipeline for swing trade candidates."""
import time
from datetime import datetime
from fmp_client import FMPClient, BudgetExhausted
from stock_universe import get_stocks_by_sector
from scoring import (
    calculate_ath,
    calculate_pct_below_ath,
    calculate_upside,
    passes_filters,
    score_stock,
    rank_stocks,
)

# Only scan top 3 winning sectors to stay within 250 calls/day free tier.
# Top 3 sectors = ~120-170 stocks = ~170 quote calls + ~30 historical = ~200 max
MAX_SECTORS = 3


class Scanner:
    def __init__(self, client: FMPClient, config: dict = None):
        self.client = client
        self.config = config or {
            "market_cap_min": 1_000_000_000,
            "volume_min": 500_000,
            "ath_min": 10.0,
            "ath_max": 60.0,
            "top_n": 15,
        }

    def get_winning_sectors(self) -> list[dict]:
        """Step 1: Get top 3 sectors outperforming the market."""
        sectors = self.client.get_sector_performance()
        winning = [
            s for s in sectors
            if float(s.get("changesPercentage", "0").replace("%", "")) > 0
        ]
        winning.sort(
            key=lambda s: float(s["changesPercentage"].replace("%", "")),
            reverse=True,
        )
        return winning[:MAX_SECTORS]

    def get_candidates(self, sectors: list[dict]) -> list[dict]:
        """Step 2: Get stocks from embedded universe in winning sectors."""
        candidates = []
        for sector_data in sectors:
            fmp_sector_name = sector_data["sector"]
            sector_perf = float(
                sector_data["changesPercentage"].replace("%", "")
            )
            stocks = get_stocks_by_sector(fmp_sector_name)
            for stock in stocks:
                candidates.append({
                    "symbol": stock["symbol"],
                    "name": stock["name"],
                    "sector": fmp_sector_name,
                    "sector_performance": sector_perf,
                })
        return candidates

    def quick_filter(self, candidate: dict) -> dict | None:
        """Step 3a: Quick filter using quote data.

        Uses 52-week high as initial screen. Passes liberally since the
        true ATH (from 5 years of history) may be much higher than the
        52-week high — a stock near its 52-week high could still be 30%
        below its multi-year ATH.
        """
        symbol = candidate["symbol"]
        quote = self.client.get_quote(symbol)

        price = quote.get("price", 0)
        year_high = quote.get("yearHigh", 0)

        if price == 0 or year_high == 0:
            return None

        pct_below_52w = ((year_high - price) / year_high) * 100

        # Only reject if WAY too far below (clearly distressed beyond range).
        # Stocks near their 52-week high still pass because their 5-year ATH
        # might be much higher.
        if pct_below_52w > (self.config["ath_max"] + 20):
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
        """Step 3b: Get 5-year historical data for true ATH, then score."""
        symbol = candidate["symbol"]

        historical = self.client.get_historical_prices(symbol)
        hist_data = historical.get("historical", [])
        ath = calculate_ath(hist_data)

        if ath is None:
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
        1. Get sector performance -> find top 3 winning sectors
        2. Get candidates from S&P 500 universe in those sectors
        3a. Quick filter: get quote, check 52-week range
        3b. Deep enrich: get 5-year historical prices for true ATH, score
        4. Rank and return top N

        Handles BudgetExhausted gracefully by returning partial results.
        """
        start_time = time.time()
        budget_warning = None

        # Step 1: Sector performance
        if progress_callback:
            progress_callback("Analyzing sector performance...")
        winning_sectors = self.get_winning_sectors()

        # Step 2: Get candidates from universe
        if progress_callback:
            progress_callback(
                f"Found {len(winning_sectors)} top sectors, "
                f"loading candidates..."
            )
        candidates = self.get_candidates(winning_sectors)

        # Step 3a: Quick filter with quotes
        quick_passed = []
        total = len(candidates)
        for i, candidate in enumerate(candidates):
            if progress_callback and i % 10 == 0:
                progress_callback(
                    f"Screening {i+1}/{total}: {candidate['symbol']}... "
                    f"({self.client.calls_made}/{self.client.call_budget} "
                    f"API calls)"
                )
            try:
                result = self.quick_filter(candidate)
                if result:
                    quick_passed.append(result)
            except BudgetExhausted as e:
                budget_warning = str(e)
                if progress_callback:
                    progress_callback(
                        f"API budget reached at {i+1}/{total}. "
                        f"Continuing with {len(quick_passed)} candidates..."
                    )
                break
            except Exception:
                continue

        # Step 3b: Deep enrich with historical data
        enriched = []
        for i, candidate in enumerate(quick_passed):
            if progress_callback:
                progress_callback(
                    f"Deep analysis {i+1}/{len(quick_passed)}: "
                    f"{candidate['symbol']}... "
                    f"({self.client.calls_made}/{self.client.call_budget} "
                    f"API calls)"
                )
            try:
                result = self.enrich_candidate(candidate)
                if result and passes_filters(
                    result,
                    ath_min=self.config["ath_min"],
                    ath_max=self.config["ath_max"],
                ):
                    enriched.append(result)
            except BudgetExhausted as e:
                budget_warning = str(e)
                if progress_callback:
                    progress_callback(
                        f"API budget reached during enrichment. "
                        f"Continuing with {len(enriched)} scored stocks..."
                    )
                break
            except Exception:
                continue

        # Step 4: Rank
        if progress_callback:
            progress_callback("Ranking candidates...")
        ranked = rank_stocks(enriched, limit=self.config["top_n"])

        elapsed = round(time.time() - start_time, 1)

        result = {
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
                "api_calls_used": self.client.calls_made,
                "elapsed_seconds": elapsed,
            },
        }

        if budget_warning:
            result["scan_metadata"]["budget_warning"] = budget_warning

        return result
