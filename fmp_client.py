import requests


class FMPClient:
    """Wrapper for Financial Modeling Prep API."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://financialmodelingprep.com/api/v3"

    def _get(self, endpoint: str, params: dict = None) -> dict | list:
        """Make GET request to FMP API."""
        if params is None:
            params = {}
        params["apikey"] = self.api_key

        resp = requests.get(f"{self.base_url}/{endpoint}", params=params, timeout=30)
        if resp.status_code != 200:
            raise Exception(f"FMP API error {resp.status_code}: {resp.text}")
        return resp.json()

    def get_sector_performance(self) -> list[dict]:
        """Get current sector performance data."""
        return self._get("sectors-performance")

    def screen_stocks(
        self,
        sector: str,
        market_cap_min: int = 1_000_000_000,
        volume_min: int = 500_000,
        exchange: str = "NYSE,NASDAQ",
        limit: int = 200,
    ) -> list[dict]:
        """Screen stocks by sector and fundamental filters."""
        return self._get("stock-screener", params={
            "sector": sector,
            "marketCapMoreThan": market_cap_min,
            "volumeMoreThan": volume_min,
            "exchange": exchange,
            "isActivelyTrading": True,
            "limit": limit,
        })

    def get_quote(self, symbol: str) -> dict:
        """Get real-time quote for a single stock."""
        data = self._get(f"quote/{symbol}")
        if not data:
            raise Exception(f"No quote data for {symbol}")
        return data[0]

    def get_batch_quotes(self, symbols: list[str]) -> list[dict]:
        """Get quotes for multiple stocks in one call."""
        symbols_str = ",".join(symbols)
        resp = requests.get(
            f"{self.base_url}/quote/{symbols_str}",
            params={"apikey": self.api_key},
            timeout=30,
        )
        if resp.status_code != 200:
            raise Exception(f"FMP API error {resp.status_code}: {resp.text}")
        return resp.json()

    def get_historical_prices(self, symbol: str, timeseries: int = 365) -> dict:
        """Get historical daily prices for ATH calculation."""
        return self._get(
            f"historical-price-full/{symbol}",
            params={"timeseries": timeseries},
        )
