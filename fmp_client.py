import requests
from datetime import datetime, timedelta


class FMPClient:
    """Wrapper for Financial Modeling Prep stable API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://financialmodelingprep.com/stable"

    def _get(self, endpoint: str, params: dict = None) -> dict | list:
        """Make GET request to FMP stable API."""
        if params is None:
            params = {}
        params["apikey"] = self.api_key

        resp = requests.get(f"{self.base_url}/{endpoint}", params=params, timeout=30)
        if resp.status_code != 200:
            raise Exception(f"FMP API error {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def get_sector_performance(self, date: str = None) -> list[dict]:
        """Get sector performance snapshot for a given date.

        Returns performance by sector and exchange. We aggregate across
        NYSE and NASDAQ to get overall sector performance.
        """
        if date is None:
            # Use last trading day (skip weekends)
            today = datetime.now()
            if today.weekday() == 0:  # Monday
                date = (today - timedelta(days=3)).strftime("%Y-%m-%d")
            elif today.weekday() == 6:  # Sunday
                date = (today - timedelta(days=2)).strftime("%Y-%m-%d")
            else:
                date = (today - timedelta(days=1)).strftime("%Y-%m-%d")

        data = self._get("sector-performance-snapshot", params={"date": date})

        # Aggregate across exchanges (NYSE + NASDAQ)
        sector_totals = {}
        sector_counts = {}
        for entry in data:
            sector = entry["sector"]
            change = entry.get("averageChange", 0)
            if sector not in sector_totals:
                sector_totals[sector] = 0
                sector_counts[sector] = 0
            sector_totals[sector] += change
            sector_counts[sector] += 1

        # Average across exchanges
        result = []
        for sector in sector_totals:
            avg = sector_totals[sector] / sector_counts[sector] if sector_counts[sector] > 0 else 0
            result.append({
                "sector": sector,
                "changesPercentage": str(round(avg, 4)),
            })

        return result

    def get_quote(self, symbol: str) -> dict:
        """Get real-time quote for a single stock."""
        data = self._get("quote", params={"symbol": symbol})
        if not data:
            raise Exception(f"No quote data for {symbol}")
        return data[0]

    def get_historical_prices(self, symbol: str, timeseries: int = 365) -> dict:
        """Get historical daily prices for ATH calculation."""
        data = self._get(
            "historical-price-eod/full",
            params={"symbol": symbol, "timeseries": timeseries},
        )
        # New API returns a flat list; wrap in expected format
        if isinstance(data, list):
            return {"symbol": symbol, "historical": data}
        return data
