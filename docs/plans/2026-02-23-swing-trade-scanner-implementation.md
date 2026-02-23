# Swing Trade Scanner Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Flask web app that screens the stock market using Financial Modeling Prep API and outputs a ranked list of swing trade candidates in a clean HTML report + CSV.

**Architecture:** Flask backend calls FMP API through a client wrapper, runs a 4-step screening pipeline (sector filter → stock screener → enrich/score → rank), and serves results to a vanilla HTML/CSS/JS frontend. All scoring logic is in a pure-function module for testability.

**Tech Stack:** Python 3.10+, Flask, requests, python-dotenv. No frontend framework.

---

### Task 1: Project Scaffolding & Dependencies

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `output/.gitkeep`

**Step 1: Create requirements.txt**

```
Flask==3.1.0
requests==2.32.3
python-dotenv==1.0.1
pytest==8.3.4
```

**Step 2: Create .env.example**

```
FMP_API_KEY=your_api_key_here
```

**Step 3: Create output directory placeholder**

```bash
mkdir -p output && touch output/.gitkeep
```

**Step 4: Install dependencies**

Run: `pip install -r requirements.txt`
Expected: All packages install successfully

**Step 5: Commit**

```bash
git add requirements.txt .env.example output/.gitkeep
git commit -m "feat: add project scaffolding and dependencies"
```

---

### Task 2: FMP API Client

**Files:**
- Create: `fmp_client.py`
- Create: `tests/test_fmp_client.py`

This module wraps all FMP API calls. Every method returns parsed JSON. Handles API key injection and error handling.

**Step 1: Write failing tests**

```python
# tests/test_fmp_client.py
import pytest
from unittest.mock import patch, Mock
from fmp_client import FMPClient


@pytest.fixture
def client():
    return FMPClient(api_key="test_key")


class TestFMPClientInit:
    def test_stores_api_key(self, client):
        assert client.api_key == "test_key"

    def test_base_url(self, client):
        assert client.base_url == "https://financialmodelingprep.com/api/v3"


class TestGetSectorPerformance:
    @patch("fmp_client.requests.get")
    def test_returns_sector_data(self, mock_get, client):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value=[
                {"sector": "Technology", "changesPercentage": "2.35"},
                {"sector": "Energy", "changesPercentage": "1.10"},
            ])
        )
        result = client.get_sector_performance()
        assert len(result) == 2
        assert result[0]["sector"] == "Technology"
        mock_get.assert_called_once_with(
            "https://financialmodelingprep.com/api/v3/sectors-performance",
            params={"apikey": "test_key"},
            timeout=30,
        )

    @patch("fmp_client.requests.get")
    def test_handles_api_error(self, mock_get, client):
        mock_get.return_value = Mock(status_code=401, text="Unauthorized")
        with pytest.raises(Exception, match="FMP API error 401"):
            client.get_sector_performance()


class TestScreenStocks:
    @patch("fmp_client.requests.get")
    def test_screens_by_sector(self, mock_get, client):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value=[
                {"symbol": "AAPL", "companyName": "Apple Inc", "sector": "Technology",
                 "marketCap": 3000000000000, "volume": 50000000, "price": 180.0},
            ])
        )
        result = client.screen_stocks(
            sector="Technology",
            market_cap_min=1_000_000_000,
            volume_min=500_000,
        )
        assert len(result) == 1
        assert result[0]["symbol"] == "AAPL"
        call_args = mock_get.call_args
        assert call_args[1]["params"]["sector"] == "Technology"
        assert call_args[1]["params"]["marketCapMoreThan"] == 1_000_000_000
        assert call_args[1]["params"]["volumeMoreThan"] == 500_000

    @patch("fmp_client.requests.get")
    def test_screens_multiple_exchanges(self, mock_get, client):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value=[])
        )
        client.screen_stocks(sector="Energy")
        call_args = mock_get.call_args
        assert call_args[1]["params"]["exchange"] == "NYSE,NASDAQ"


class TestGetQuote:
    @patch("fmp_client.requests.get")
    def test_returns_quote_data(self, mock_get, client):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value=[{
                "symbol": "AAPL", "price": 180.0, "yearHigh": 200.0,
                "yearLow": 140.0, "volume": 50000000, "avgVolume": 45000000,
                "name": "Apple Inc",
            }])
        )
        result = client.get_quote("AAPL")
        assert result["symbol"] == "AAPL"
        assert result["price"] == 180.0


class TestGetHistoricalPrices:
    @patch("fmp_client.requests.get")
    def test_returns_historical_data(self, mock_get, client):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "symbol": "AAPL",
                "historical": [
                    {"date": "2026-02-20", "high": 180.0},
                    {"date": "2025-06-15", "high": 220.0},
                ]
            })
        )
        result = client.get_historical_prices("AAPL", timeseries=365)
        assert result["symbol"] == "AAPL"
        assert len(result["historical"]) == 2


class TestGetBatchQuotes:
    @patch("fmp_client.requests.get")
    def test_batch_quotes(self, mock_get, client):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value=[
                {"symbol": "AAPL", "price": 180.0},
                {"symbol": "MSFT", "price": 420.0},
            ])
        )
        result = client.get_batch_quotes(["AAPL", "MSFT"])
        assert len(result) == 2
        # Verify comma-separated symbols in URL
        call_url = mock_get.call_args[0][0]
        assert "AAPL,MSFT" in call_url
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_fmp_client.py -v`
Expected: All tests FAIL with `ModuleNotFoundError: No module named 'fmp_client'`

**Step 3: Implement FMP client**

```python
# fmp_client.py
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
        """Get quotes for multiple stocks in one call (up to ~50)."""
        symbols_str = ",".join(symbols)
        return requests.get(
            f"{self.base_url}/quote/{symbols_str}",
            params={"apikey": self.api_key},
            timeout=30,
        ).json()

    def get_historical_prices(self, symbol: str, timeseries: int = 365) -> dict:
        """Get historical daily prices for ATH calculation."""
        return self._get(
            f"historical-price-full/{symbol}",
            params={"timeseries": timeseries},
        )
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_fmp_client.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add fmp_client.py tests/test_fmp_client.py
git commit -m "feat: add FMP API client with full test coverage"
```

---

### Task 3: Scoring Module

**Files:**
- Create: `scoring.py`
- Create: `tests/test_scoring.py`

Pure functions. No API calls. Calculates composite scores for ranking stocks.

**Step 1: Write failing tests**

```python
# tests/test_scoring.py
import pytest
from scoring import (
    calculate_ath,
    calculate_pct_below_ath,
    calculate_upside,
    score_stock,
    rank_stocks,
    passes_filters,
)


class TestCalculateATH:
    def test_finds_highest_price(self):
        historical = [
            {"high": 100.0}, {"high": 150.0}, {"high": 120.0}
        ]
        assert calculate_ath(historical) == 150.0

    def test_empty_history_returns_none(self):
        assert calculate_ath([]) is None

    def test_single_entry(self):
        assert calculate_ath([{"high": 99.5}]) == 99.5


class TestCalculatePctBelowATH:
    def test_basic_calculation(self):
        # Price 80, ATH 100 = 20% below
        assert calculate_pct_below_ath(80.0, 100.0) == pytest.approx(20.0)

    def test_at_ath(self):
        assert calculate_pct_below_ath(100.0, 100.0) == pytest.approx(0.0)

    def test_50_pct_below(self):
        assert calculate_pct_below_ath(50.0, 100.0) == pytest.approx(50.0)


class TestCalculateUpside:
    def test_basic_upside(self):
        # Price 80, target 100 = 25% upside
        assert calculate_upside(80.0, 100.0) == pytest.approx(25.0)

    def test_zero_upside(self):
        assert calculate_upside(100.0, 100.0) == pytest.approx(0.0)


class TestPassesFilters:
    def test_passes_with_valid_stock(self):
        stock = {
            "pct_below_ath": 25.0,
            "price": 75.0,
            "yearHigh": 100.0,
            "yearLow": 50.0,
            "volume": 1000000,
            "avgVolume": 900000,
        }
        assert passes_filters(stock, ath_min=15.0, ath_max=50.0) is True

    def test_fails_ath_too_low(self):
        stock = {
            "pct_below_ath": 10.0,
            "price": 90.0,
            "yearHigh": 100.0,
            "yearLow": 50.0,
            "volume": 1000000,
            "avgVolume": 900000,
        }
        assert passes_filters(stock, ath_min=15.0, ath_max=50.0) is False

    def test_fails_ath_too_high(self):
        stock = {
            "pct_below_ath": 60.0,
            "price": 40.0,
            "yearHigh": 100.0,
            "yearLow": 30.0,
            "volume": 1000000,
            "avgVolume": 900000,
        }
        assert passes_filters(stock, ath_min=15.0, ath_max=50.0) is False


class TestScoreStock:
    def test_returns_score_between_0_and_100(self):
        stock = {
            "pct_below_ath": 30.0,
            "upside_pct": 42.8,
            "sector_performance": 2.5,
            "volume": 5000000,
            "avgVolume": 4000000,
            "price": 70.0,
            "yearLow": 50.0,
            "yearHigh": 100.0,
        }
        score = score_stock(stock)
        assert 0 <= score <= 100

    def test_higher_upside_scores_higher(self):
        base = {
            "sector_performance": 2.0,
            "volume": 1000000,
            "avgVolume": 1000000,
            "price": 70.0,
            "yearLow": 50.0,
            "yearHigh": 100.0,
        }
        low_upside = {**base, "pct_below_ath": 15.0, "upside_pct": 17.6}
        high_upside = {**base, "pct_below_ath": 40.0, "upside_pct": 66.7}
        assert score_stock(high_upside) > score_stock(low_upside)


class TestRankStocks:
    def test_sorts_by_score_descending(self):
        stocks = [
            {"symbol": "A", "score": 60},
            {"symbol": "B", "score": 80},
            {"symbol": "C", "score": 70},
        ]
        ranked = rank_stocks(stocks, limit=10)
        assert [s["symbol"] for s in ranked] == ["B", "C", "A"]

    def test_respects_limit(self):
        stocks = [
            {"symbol": "A", "score": 60},
            {"symbol": "B", "score": 80},
            {"symbol": "C", "score": 70},
        ]
        ranked = rank_stocks(stocks, limit=2)
        assert len(ranked) == 2

    def test_adds_rank_field(self):
        stocks = [{"symbol": "A", "score": 80}, {"symbol": "B", "score": 60}]
        ranked = rank_stocks(stocks, limit=10)
        assert ranked[0]["rank"] == 1
        assert ranked[1]["rank"] == 2
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scoring.py -v`
Expected: All tests FAIL with `ModuleNotFoundError: No module named 'scoring'`

**Step 3: Implement scoring module**

```python
# scoring.py
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
    upside_score = upside  # 0-100 directly

    # Sector score: normalize sector performance (-5 to +5 range typical)
    sector_perf = stock.get("sector_performance", 0)
    sector_score = max(0, min(100, (sector_perf + 5) * 10))

    # Volume trend: current volume vs average (>1 = accumulation signal)
    volume = stock.get("volume", 0)
    avg_volume = stock.get("avgVolume", 1)
    vol_ratio = volume / avg_volume if avg_volume > 0 else 1.0
    volume_score = max(0, min(100, vol_ratio * 50))  # 2x avg = 100

    # Value positioning: how close to 52-week low (closer = more value)
    price = stock.get("price", 0)
    year_low = stock.get("yearLow", 0)
    year_high = stock.get("yearHigh", 1)
    year_range = year_high - year_low
    if year_range > 0:
        # 0 = at year high (no value), 100 = at year low (max value)
        value_score = ((year_high - price) / year_range) * 100
    else:
        value_score = 50

    # Weighted composite
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
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scoring.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add scoring.py tests/test_scoring.py
git commit -m "feat: add scoring module with composite conviction scoring"
```

---

### Task 4: Scanner Pipeline

**Files:**
- Create: `scanner.py`
- Create: `tests/test_scanner.py`

Orchestrates the 4-step screening pipeline. Uses FMPClient and scoring module.

**Step 1: Write failing tests**

```python
# tests/test_scanner.py
import pytest
from unittest.mock import Mock, patch, MagicMock
from scanner import Scanner


@pytest.fixture
def mock_client():
    client = Mock()
    client.get_sector_performance.return_value = [
        {"sector": "Technology", "changesPercentage": "2.35"},
        {"sector": "Energy", "changesPercentage": "1.10"},
        {"sector": "Healthcare", "changesPercentage": "-0.50"},
        {"sector": "Utilities", "changesPercentage": "-1.20"},
    ]
    return client


@pytest.fixture
def scanner(mock_client):
    return Scanner(client=mock_client)


class TestGetWinningSectors:
    def test_returns_positive_sectors(self, scanner, mock_client):
        sectors = scanner.get_winning_sectors()
        # Only sectors with positive performance
        sector_names = [s["sector"] for s in sectors]
        assert "Technology" in sector_names
        assert "Energy" in sector_names
        assert "Healthcare" not in sector_names

    def test_sorts_by_performance_desc(self, scanner):
        sectors = scanner.get_winning_sectors()
        perfs = [float(s["changesPercentage"]) for s in sectors]
        assert perfs == sorted(perfs, reverse=True)


class TestGetCandidates:
    def test_screens_each_winning_sector(self, scanner, mock_client):
        mock_client.screen_stocks.return_value = [
            {"symbol": "AAPL", "companyName": "Apple", "sector": "Technology"}
        ]
        candidates = scanner.get_candidates(
            [{"sector": "Technology", "changesPercentage": "2.35"},
             {"sector": "Energy", "changesPercentage": "1.10"}]
        )
        assert mock_client.screen_stocks.call_count == 2

    def test_deduplicates_stocks(self, scanner, mock_client):
        mock_client.screen_stocks.return_value = [
            {"symbol": "AAPL", "companyName": "Apple", "sector": "Technology"}
        ]
        candidates = scanner.get_candidates(
            [{"sector": "Technology", "changesPercentage": "2.35"},
             {"sector": "Technology", "changesPercentage": "2.35"}]
        )
        # Same stock returned twice, should be deduplicated
        symbols = [c["symbol"] for c in candidates]
        assert symbols.count("AAPL") == 1


class TestEnrichCandidate:
    def test_adds_ath_and_upside(self, scanner, mock_client):
        mock_client.get_quote.return_value = {
            "symbol": "AAPL", "price": 150.0, "yearHigh": 200.0,
            "yearLow": 120.0, "volume": 5000000, "avgVolume": 4000000,
            "name": "Apple Inc",
        }
        mock_client.get_historical_prices.return_value = {
            "symbol": "AAPL",
            "historical": [
                {"high": 180.0}, {"high": 220.0}, {"high": 190.0}
            ]
        }
        candidate = {"symbol": "AAPL", "sector": "Technology"}
        enriched = scanner.enrich_candidate(candidate, sector_perf=2.35)
        assert enriched["ath"] == 220.0
        assert enriched["pct_below_ath"] == pytest.approx(31.8, abs=0.1)
        assert "upside_pct" in enriched
        assert "score" in enriched


class TestRunScan:
    def test_full_pipeline_returns_ranked_results(self, scanner, mock_client):
        mock_client.screen_stocks.return_value = [
            {"symbol": "AAPL", "sector": "Technology"},
            {"symbol": "MSFT", "sector": "Technology"},
        ]
        mock_client.get_quote.side_effect = [
            {"symbol": "AAPL", "price": 150.0, "yearHigh": 200.0,
             "yearLow": 120.0, "volume": 5000000, "avgVolume": 4000000,
             "name": "Apple Inc"},
            {"symbol": "MSFT", "price": 350.0, "yearHigh": 430.0,
             "yearLow": 300.0, "volume": 3000000, "avgVolume": 2500000,
             "name": "Microsoft Corp"},
        ]
        mock_client.get_historical_prices.side_effect = [
            {"symbol": "AAPL", "historical": [{"high": 220.0}]},
            {"symbol": "MSFT", "historical": [{"high": 450.0}]},
        ]

        results = scanner.run_scan()
        assert isinstance(results, dict)
        assert "stocks" in results
        assert "scan_metadata" in results
        assert results["scan_metadata"]["total_candidates"] >= 0
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_scanner.py -v`
Expected: All tests FAIL with `ModuleNotFoundError: No module named 'scanner'`

**Step 3: Implement scanner pipeline**

```python
# scanner.py
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
        # Filter for positive performance and sort descending
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

        # Get quote data
        quote = self.client.get_quote(symbol)

        # Get historical for ATH
        historical = self.client.get_historical_prices(symbol, timeseries=365)
        hist_data = historical.get("historical", [])
        ath = calculate_ath(hist_data)

        if ath is None or quote.get("price", 0) == 0:
            return None

        price = quote["price"]
        pct_below = calculate_pct_below_ath(price, ath)
        target = ath  # Target is the all-time high
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

        # Score the stock
        enriched["score"] = score_stock(enriched)

        return enriched

    def run_scan(self, progress_callback=None) -> dict:
        """Run the full 4-step screening pipeline."""
        start_time = time.time()

        # Step 1: Sector filter
        if progress_callback:
            progress_callback("Analyzing sector performance...")
        winning_sectors = self.get_winning_sectors()

        # Step 2: Screen stocks
        if progress_callback:
            progress_callback(
                f"Screening stocks in {len(winning_sectors)} outperforming sectors..."
            )
        candidates = self.get_candidates(winning_sectors)

        # Step 3: Enrich and score
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
                continue  # Skip stocks that fail enrichment

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
                "passed_filters": len(enriched),
                "elapsed_seconds": elapsed,
            },
        }
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scanner.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add scanner.py tests/test_scanner.py
git commit -m "feat: add scanner pipeline with 4-step screening logic"
```

---

### Task 5: Flask App & API Routes

**Files:**
- Create: `app.py`
- Create: `tests/test_app.py`

**Step 1: Write failing tests**

```python
# tests/test_app.py
import pytest
import json
from unittest.mock import patch, Mock
from app import create_app


@pytest.fixture
def client():
    app = create_app(testing=True)
    with app.test_client() as client:
        yield client


class TestIndexRoute:
    def test_serves_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Swing Trade Scanner" in resp.data


class TestScanRoute:
    @patch("app.Scanner")
    @patch("app.FMPClient")
    def test_returns_scan_results(self, mock_fmp_cls, mock_scanner_cls, client):
        mock_scanner = Mock()
        mock_scanner.run_scan.return_value = {
            "stocks": [{"symbol": "AAPL", "score": 75.0, "rank": 1}],
            "scan_metadata": {"total_candidates": 50},
        }
        mock_scanner_cls.return_value = mock_scanner
        mock_fmp_cls.return_value = Mock()

        resp = client.post("/api/scan")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "stocks" in data
        assert len(data["stocks"]) == 1

    @patch("app.os")
    def test_returns_error_without_api_key(self, mock_os, client):
        mock_os.getenv.return_value = None
        resp = client.post("/api/scan")
        assert resp.status_code == 400


class TestCSVRoute:
    @patch("app.Scanner")
    @patch("app.FMPClient")
    def test_returns_csv(self, mock_fmp_cls, mock_scanner_cls, client):
        mock_scanner = Mock()
        mock_scanner.run_scan.return_value = {
            "stocks": [{
                "rank": 1, "symbol": "AAPL", "name": "Apple",
                "sector": "Technology", "price": 150.0, "ath": 220.0,
                "pct_below_ath": 31.8, "target_price": 220.0,
                "upside_pct": 46.7, "score": 75.0,
            }],
            "scan_metadata": {"total_candidates": 50},
        }
        mock_scanner_cls.return_value = mock_scanner
        mock_fmp_cls.return_value = Mock()

        resp = client.get("/api/csv")
        assert resp.status_code == 200
        assert resp.content_type == "text/csv; charset=utf-8"
        assert b"AAPL" in resp.data
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_app.py -v`
Expected: All tests FAIL with `ModuleNotFoundError: No module named 'app'`

**Step 3: Implement Flask app**

```python
# app.py
"""Flask web app for Swing Trade Scanner."""
import os
import io
import csv
import json
from datetime import datetime
from flask import Flask, render_template, jsonify, request, Response
from dotenv import load_dotenv
from fmp_client import FMPClient
from scanner import Scanner

load_dotenv()


def create_app(testing=False):
    app = Flask(__name__)
    app.config["TESTING"] = testing

    # Store latest scan results in memory for CSV download
    app.latest_scan = None

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/scan", methods=["POST"])
    def run_scan():
        api_key = os.getenv("FMP_API_KEY")
        if not api_key or api_key == "your_api_key_here":
            return jsonify({"error": "FMP API key not configured. Add your key to .env file."}), 400

        try:
            # Get optional config overrides from request
            config = {
                "market_cap_min": 1_000_000_000,
                "volume_min": 500_000,
                "ath_min": 15.0,
                "ath_max": 50.0,
                "top_n": 15,
            }
            if request.json:
                config.update({
                    k: v for k, v in request.json.items() if k in config
                })

            client = FMPClient(api_key=api_key)
            scanner = Scanner(client=client, config=config)
            results = scanner.run_scan()

            # Save results
            app.latest_scan = results
            _save_report(results)

            return jsonify(results)

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/csv")
    def download_csv():
        if not app.latest_scan:
            # Run a fresh scan
            api_key = os.getenv("FMP_API_KEY")
            if not api_key:
                return jsonify({"error": "No scan data available"}), 400
            client = FMPClient(api_key=api_key)
            scanner = Scanner(client=client)
            app.latest_scan = scanner.run_scan()

        stocks = app.latest_scan.get("stocks", [])
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Rank", "Ticker", "Name", "Sector", "Sector Performance %",
            "Current Price", "52-Week High", "All-Time High",
            "% Below ATH", "Target Price", "Potential Upside %",
            "Conviction Score",
        ])
        for stock in stocks:
            writer.writerow([
                stock.get("rank", ""),
                stock.get("symbol", ""),
                stock.get("name", ""),
                stock.get("sector", ""),
                stock.get("sector_performance", ""),
                stock.get("price", ""),
                stock.get("yearHigh", ""),
                stock.get("ath", ""),
                stock.get("pct_below_ath", ""),
                stock.get("target_price", ""),
                stock.get("upside_pct", ""),
                stock.get("score", ""),
            ])

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=swing_scan_{datetime.now().strftime('%Y%m%d')}.csv"},
        )

    return app


def _save_report(results: dict):
    """Save scan results as JSON to output directory."""
    os.makedirs("output", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = f"output/scan_{timestamp}.json"
    with open(filepath, "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    app = create_app()
    print("\n  Swing Trade Scanner running at http://localhost:5000\n")
    app.run(debug=True, port=5000)
```

**Step 4: Create empty template so Flask doesn't crash**

Create `templates/index.html` with placeholder content:

```html
<!DOCTYPE html>
<html><head><title>Swing Trade Scanner</title></head>
<body><h1>Swing Trade Scanner</h1><p>UI coming next...</p></body>
</html>
```

**Step 5: Run tests to verify they pass**

Run: `pytest tests/test_app.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add app.py tests/test_app.py templates/index.html
git commit -m "feat: add Flask app with scan and CSV download endpoints"
```

---

### Task 6: Frontend UI

**Files:**
- Modify: `templates/index.html`

This is the full frontend — HTML + embedded CSS + vanilla JS. No framework. One file.

**Step 1: Build the complete index.html**

The HTML file should include:
- Clean header with "Swing Trade Scanner" title and last-run timestamp
- "Run Scan" button (large, green, prominent)
- Loading overlay with animated spinner and progress messages
- Results table with all 10 columns from the design doc
- Color-coded rows: green background for top 5 (high conviction), yellow for 6-10 (medium), neutral for rest
- Expandable row detail on click (sector rank, volume vs avg, 52-week range bar)
- "Download CSV" button below results
- Settings panel (collapsible) for: API key status indicator, ATH range sliders, market cap minimum
- Footer with scan metadata (sectors analyzed, candidates screened, time elapsed)
- Responsive design that works on desktop and tablet
- Dark/light professional color scheme (financial dashboard aesthetic)

The JavaScript should:
- `POST /api/scan` when "Run Scan" is clicked
- Show loading overlay with progress messages
- Render results table dynamically from JSON response
- Handle errors gracefully (show error message, suggest checking API key)
- Download CSV via `/api/csv` link
- Store last scan time in localStorage

**NOTE**: This is a large UI file. The implementing engineer should use the `frontend-design` skill for this task to ensure high design quality.

**Step 2: Manual test**

Run: `python app.py`
Open: `http://localhost:5000`
Verify: Page loads, button is visible, layout looks clean

**Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: add polished frontend UI with scan controls and results table"
```

---

### Task 7: README & Setup Instructions

**Files:**
- Create: `README.md`

**Step 1: Write README**

```markdown
# Swing Trade Scanner

A stock market swing trade scanner that screens for stocks with high upside potential using programmatic sector analysis and technical filters.

## Quick Start

### 1. Get an API Key (free, 2 minutes)

1. Go to [financialmodelingprep.com](https://financialmodelingprep.com/)
2. Click "Get Free API Key"
3. Sign up and copy your API key

### 2. Setup

```bash
# Clone the repo
git clone https://github.com/bmbx12/AI-Workspace.git
cd swing-trade-scanner

# Install dependencies
pip install -r requirements.txt

# Configure API key
cp .env.example .env
# Edit .env and paste your API key
```

### 3. Run

```bash
python app.py
```

Open `http://localhost:5000` in your browser and click **Run Scan**.

## What It Does

The scanner runs a 4-step pipeline:

1. **Sector Analysis** — Finds sectors outperforming the S&P 500
2. **Stock Screening** — Filters stocks by market cap, volume, and exchange
3. **Enrichment** — Gets price history, calculates distance from all-time high
4. **Ranking** — Scores and ranks top candidates by conviction level

## Output

Each scan produces:
- **HTML report** — Color-coded table of top 10-15 picks
- **CSV download** — For your own spreadsheets and tracking
- **JSON archive** — Saved to `output/` folder

## Scan Criteria

| Filter | Value |
|--------|-------|
| Market Cap | > $1 billion |
| Daily Volume | > 500,000 shares |
| Exchange | NYSE, NASDAQ |
| Distance from ATH | 15-50% below |
| Sectors | Outperforming S&P 500 |

## Recommended Workflow

1. Run the scanner weekly (Sunday evening)
2. Review the top 10-15 picks
3. Run picks through [Chaikin Power Gauge](https://chaikinanalytics.com/) as a confirmation filter
4. Stocks that pass both = your watchlist for the week
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup instructions"
```

---

### Task 8: Integration Test & Polish

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test (with mocked API)**

```python
# tests/test_integration.py
"""Integration test: full scan pipeline with mocked FMP API."""
import pytest
import json
from unittest.mock import patch, Mock
from app import create_app


MOCK_SECTORS = [
    {"sector": "Technology", "changesPercentage": "2.35"},
    {"sector": "Energy", "changesPercentage": "1.10"},
    {"sector": "Healthcare", "changesPercentage": "-0.50"},
]

MOCK_SCREENER = [
    {"symbol": "NVDA", "companyName": "NVIDIA Corp", "sector": "Technology",
     "marketCap": 2000000000000, "volume": 40000000, "price": 700.0},
    {"symbol": "XOM", "companyName": "Exxon Mobil", "sector": "Energy",
     "marketCap": 450000000000, "volume": 15000000, "price": 100.0},
]

MOCK_QUOTES = {
    "NVDA": {"symbol": "NVDA", "price": 700.0, "yearHigh": 950.0,
             "yearLow": 450.0, "volume": 45000000, "avgVolume": 40000000,
             "name": "NVIDIA Corporation"},
    "XOM": {"symbol": "XOM", "price": 100.0, "yearHigh": 125.0,
            "yearLow": 85.0, "volume": 18000000, "avgVolume": 15000000,
            "name": "Exxon Mobil Corporation"},
}

MOCK_HISTORICAL = {
    "NVDA": {"symbol": "NVDA", "historical": [
        {"high": 950.0}, {"high": 1050.0}, {"high": 800.0}
    ]},
    "XOM": {"symbol": "XOM", "historical": [
        {"high": 120.0}, {"high": 130.0}, {"high": 110.0}
    ]},
}


@pytest.fixture
def client():
    app = create_app(testing=True)
    with app.test_client() as c:
        yield c


@patch("app.os")
@patch("app.FMPClient")
def test_full_scan_flow(mock_fmp_cls, mock_os, client):
    mock_os.getenv.return_value = "test_key"
    mock_os.makedirs = Mock()

    mock_fmp = Mock()
    mock_fmp_cls.return_value = mock_fmp

    mock_fmp.get_sector_performance.return_value = MOCK_SECTORS
    mock_fmp.screen_stocks.return_value = MOCK_SCREENER

    def mock_quote(symbol):
        return MOCK_QUOTES[symbol]
    mock_fmp.get_quote.side_effect = mock_quote

    def mock_hist(symbol, timeseries=365):
        return MOCK_HISTORICAL[symbol]
    mock_fmp.get_historical_prices.side_effect = mock_hist

    # Patch open to avoid file writes
    with patch("builtins.open", Mock()):
        resp = client.post("/api/scan")

    assert resp.status_code == 200
    data = json.loads(resp.data)
    assert "stocks" in data
    assert "scan_metadata" in data
    assert data["scan_metadata"]["total_candidates"] >= 1

    # Verify stocks have all required fields
    if data["stocks"]:
        stock = data["stocks"][0]
        required_fields = [
            "symbol", "name", "sector", "price", "ath",
            "pct_below_ath", "target_price", "upside_pct", "score", "rank",
        ]
        for field in required_fields:
            assert field in stock, f"Missing field: {field}"
```

**Step 2: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add integration test for full scan pipeline"
```

---

### Task 9: Final Verification & Push

**Step 1: Run full test suite**

Run: `pytest tests/ -v --tb=short`
Expected: All tests PASS

**Step 2: Manual smoke test**

Run: `python app.py`
Open: `http://localhost:5000`
Verify:
- Page loads with clean design
- "Run Scan" button is visible and clickable
- Without API key: shows clear error message
- Settings panel works
- Layout is responsive

**Step 3: Push to GitHub**

```bash
git remote add origin https://github.com/bmbx12/AI-Workspace.git
git push -u origin main
```

Or if this should be a subdirectory of the existing AI-Workspace repo, adjust accordingly.
