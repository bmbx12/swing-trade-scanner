"""Core screening pipeline for swing trade candidates."""
import time
from datetime import datetime
from fmp_client import FMPClient
from scoring import (
    calculate_ath,
    calculate_pct_below_ath,
    calculate_upside,
    passes_filters,
    score_stock,
    rank_stocks,
)


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

    def get_winning_sectors(self) -> list[dict]:
        """Step 1: Get sectors outperforming the market."""
        sectors = self.client.get_sector_performance()
        winning = [
            s for s in sectors
            if float(s.get("changesPercentage", "0").replace("%", "")) > 0
        ]
        winning.sort(
            key=lambda s: float(s["changesPercentage"].replace("%", "")),
            reverse=True,
        )
        return winning

    def get_candidates(self, sectors: list[dict]) -> list[dict]:
        """Step 2: Screen stocks in winning sectors."""
        seen = set()
        candidates = []
        for sector_data in sectors:
            sector_name = sector_data["sector"]
            stocks = self.client.screen_stocks(
                sector=sector_name,
                market_cap_min=self.config["market_cap_min"],
                volume_min=self.config["volume_min"],
            )
            for stock in stocks:
                symbol = stock["symbol"]
                if symbol not in seen:
                    seen.add(symbol)
                    stock["sector_performance"] = float(
                        sector_data["changesPercentage"].replace("%", "")
                    )
                    candidates.append(stock)
        return candidates

    def enrich_candidate(self, candidate: dict, sector_perf: float) -> dict:
        """Step 3: Add quote data, ATH, and score to a candidate."""
        symbol = candidate["symbol"]

        quote = self.client.get_quote(symbol)

        historical = self.client.get_historical_prices(symbol, timeseries=365)
        hist_data = historical.get("historical", [])
        ath = calculate_ath(hist_data)

        if ath is None or quote.get("price", 0) == 0:
            return None

        price = quote["price"]
        pct_below = calculate_pct_below_ath(price, ath)
        target = ath
        upside = calculate_upside(price, target)

        enriched = {
            "symbol": symbol,
            "name": quote.get("name", candidate.get("companyName", "")),
            "sector": candidate.get("sector", ""),
            "sector_performance": sector_perf,
            "price": price,
            "yearHigh": quote.get("yearHigh", 0),
            "yearLow": quote.get("yearLow", 0),
            "volume": quote.get("volume", 0),
            "avgVolume": quote.get("avgVolume", 0),
            "ath": ath,
            "pct_below_ath": round(pct_below, 1),
            "target_price": round(target, 2),
            "upside_pct": round(upside, 1),
        }

        enriched["score"] = score_stock(enriched)
        return enriched

    def run_scan(self, progress_callback=None) -> dict:
        """Run the full 4-step screening pipeline."""
        start_time = time.time()

        if progress_callback:
            progress_callback("Analyzing sector performance...")
        winning_sectors = self.get_winning_sectors()

        if progress_callback:
            progress_callback(
                f"Screening stocks in {len(winning_sectors)} outperforming sectors..."
            )
        candidates = self.get_candidates(winning_sectors)

        enriched = []
        total = len(candidates)
        for i, candidate in enumerate(candidates):
            if progress_callback and i % 10 == 0:
                progress_callback(
                    f"Analyzing stock {i+1}/{total}: {candidate['symbol']}..."
                )
            try:
                sector_perf = candidate.get("sector_performance", 0)
                result = self.enrich_candidate(candidate, sector_perf)
                if result and passes_filters(
                    result,
                    ath_min=self.config["ath_min"],
                    ath_max=self.config["ath_max"],
                ):
                    enriched.append(result)
            except Exception:
                continue

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
                "passed_filters": len(enriched),
                "elapsed_seconds": elapsed,
            },
        }
