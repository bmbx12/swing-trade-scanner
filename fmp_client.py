import time
import requests
from datetime import datetime, timedelta


class BudgetExhausted(Exception):
    """Raised when the API call budget has been reached."""
    pass


class FMPClient:
    """Wrapper for Financial Modeling Prep stable API.

    Tracks API call count against a budget to stay within free tier limits
    (250 calls/day). Adds rate limiting between calls to avoid 429 errors.
    """

    def __init__(self, api_key: str, call_budget: int = 200):
        self.api_key = api_key
        self.base_url = "https://financialmodelingprep.com/stable"
        self.call_budget = call_budget
        self.calls_made = 0

    def _get(self, endpoint: str, params: dict = None) -> dict | list:
        """Make GET request to FMP stable API."""
        if self.calls_made >= self.call_budget:
            raise BudgetExhausted(
                f"API call budget of {self.call_budget} reached "
                f"({self.calls_made} calls made)"
            )

        if params is None:
            params = {}
        params["apikey"] = self.api_key

        # Rate limit: 150ms between calls to avoid burst 429s
        if self.calls_made > 0:
            time.sleep(0.15)

        self.calls_made += 1
        resp = requests.get(
            f"{self.base_url}/{endpoint}", params=params, timeout=30
        )
        if resp.status_code == 429:
            raise BudgetExhausted(
                f"FMP rate limit hit after {self.calls_made} calls. "
                "Daily limit (250) likely reached."
            )
        if resp.status_code != 200:
            raise Exception(
                f"FMP API error {resp.status_code}: {resp.text[:200]}"
            )
        return resp.json()

    def get_sector_performance(self, date: str = None) -> list[dict]:
        """Get sector performance snapshot for a given date.

        Returns performance by sector and exchange. We aggregate across
        NYSE and NASDAQ to get overall sector performance.
        """
        if date is None:
            today = datetime.now()
            if today.weekday() == 0:  # Monday
                date = (today - timedelta(days=3)).strftime("%Y-%m-%d")
            elif today.weekday() == 6:  # Sunday
                date = (today - timedelta(days=2)).strftime("%Y-%m-%d")
            else:
                date = (today - timedelta(days=1)).strftime("%Y-%m-%d")

        data = self._get("sector-performance-snapshot", params={"date": date})

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

        result = []
        for sector in sector_totals:
            avg = (
                sector_totals[sector] / sector_counts[sector]
                if sector_counts[sector] > 0
                else 0
            )
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

    def get_historical_prices(
        self, symbol: str, timeseries: int = 1260
    ) -> dict:
        """Get historical daily prices for ATH calculation.

        Default is 1260 trading days (~5 years) for meaningful ATH.
        """
        data = self._get(
            "historical-price-eod/full",
            params={"symbol": symbol, "timeseries": timeseries},
        )
        if isinstance(data, list):
            return {"symbol": symbol, "historical": data}
        return data
