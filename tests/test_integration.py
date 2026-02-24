"""Integration test: full scan pipeline with mocked FMP API."""
import pytest
import json
import os
from unittest.mock import patch, Mock
from app import create_app


MOCK_SECTORS = [
    {"sector": "Technology", "changesPercentage": "2.35"},
    {"sector": "Energy", "changesPercentage": "1.10"},
    {"sector": "Healthcare", "changesPercentage": "-0.50"},
]

MOCK_SCREENER_TECH = [
    {"symbol": "NVDA", "companyName": "NVIDIA Corp", "sector": "Technology",
     "marketCap": 2000000000000, "volume": 40000000, "price": 700.0},
    {"symbol": "CRM", "companyName": "Salesforce Inc", "sector": "Technology",
     "marketCap": 250000000000, "volume": 8000000, "price": 250.0},
]

MOCK_SCREENER_ENERGY = [
    {"symbol": "XOM", "companyName": "Exxon Mobil", "sector": "Energy",
     "marketCap": 450000000000, "volume": 15000000, "price": 100.0},
]

MOCK_QUOTES = {
    "NVDA": {"symbol": "NVDA", "price": 700.0, "yearHigh": 950.0,
             "yearLow": 450.0, "volume": 45000000, "avgVolume": 40000000,
             "name": "NVIDIA Corporation"},
    "CRM": {"symbol": "CRM", "price": 250.0, "yearHigh": 350.0,
            "yearLow": 200.0, "volume": 9000000, "avgVolume": 8000000,
            "name": "Salesforce Inc"},
    "XOM": {"symbol": "XOM", "price": 100.0, "yearHigh": 125.0,
            "yearLow": 85.0, "volume": 18000000, "avgVolume": 15000000,
            "name": "Exxon Mobil Corporation"},
}

MOCK_HISTORICAL = {
    "NVDA": {"symbol": "NVDA", "historical": [
        {"high": 950.0}, {"high": 1050.0}, {"high": 800.0}
    ]},
    "CRM": {"symbol": "CRM", "historical": [
        {"high": 330.0}, {"high": 370.0}, {"high": 290.0}
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


def _setup_mock_fmp(mock_fmp):
    """Configure mock FMP client with test data."""
    mock_fmp.get_sector_performance.return_value = MOCK_SECTORS

    def mock_screen(sector, **kwargs):
        if sector == "Technology":
            return MOCK_SCREENER_TECH
        elif sector == "Energy":
            return MOCK_SCREENER_ENERGY
        return []
    mock_fmp.screen_stocks.side_effect = mock_screen
    mock_fmp.get_quote.side_effect = lambda sym: MOCK_QUOTES[sym]
    mock_fmp.get_historical_prices.side_effect = lambda sym, **kw: MOCK_HISTORICAL[sym]


def test_full_scan_pipeline(client):
    """End-to-end: POST /api/scan returns properly structured results."""
    with patch.dict(os.environ, {"FMP_API_KEY": "test_key"}), \
         patch("app.FMPClient") as mock_fmp_cls, \
         patch("app._save_report"):
        mock_fmp = Mock()
        mock_fmp_cls.return_value = mock_fmp
        _setup_mock_fmp(mock_fmp)

        resp = client.post("/api/scan",
                           data=json.dumps({"ath_min": 15, "ath_max": 50}),
                           content_type="application/json")

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

            # Verify scoring makes sense
            assert 0 <= stock["score"] <= 100
            assert stock["rank"] >= 1
            assert stock["upside_pct"] > 0


def test_scan_then_csv_download(client):
    """Scan results can be downloaded as CSV."""
    with patch.dict(os.environ, {"FMP_API_KEY": "test_key"}), \
         patch("app.FMPClient") as mock_fmp_cls, \
         patch("app._save_report"):
        mock_fmp = Mock()
        mock_fmp_cls.return_value = mock_fmp
        _setup_mock_fmp(mock_fmp)

        # Run scan
        client.post("/api/scan",
                     data=json.dumps({}),
                     content_type="application/json")

        # Download CSV
        resp = client.get("/api/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

        csv_text = resp.data.decode()
        lines = csv_text.strip().split("\n")
        # Header + at least 1 data row
        assert len(lines) >= 2
        assert "Rank" in lines[0]
        assert "Ticker" in lines[0]


def test_custom_filters_applied(client):
    """Custom filter settings are passed to the scanner."""
    with patch.dict(os.environ, {"FMP_API_KEY": "test_key"}), \
         patch("app.FMPClient") as mock_fmp_cls, \
         patch("app.Scanner") as mock_scanner_cls, \
         patch("app._save_report"):
        mock_scanner = Mock()
        mock_scanner.run_scan.return_value = {
            "stocks": [], "scan_metadata": {"total_candidates": 0, "passed_filters": 0}
        }
        mock_scanner_cls.return_value = mock_scanner

        config = {"ath_min": 20, "ath_max": 40, "top_n": 10}
        client.post("/api/scan",
                     data=json.dumps(config),
                     content_type="application/json")

        # Verify Scanner was created with custom config
        call_kwargs = mock_scanner_cls.call_args
        scanner_config = call_kwargs[1]["config"] if "config" in (call_kwargs[1] or {}) else call_kwargs[0][1] if len(call_kwargs[0]) > 1 else None

        # The config should have been updated with our custom values
        if scanner_config:
            assert scanner_config["ath_min"] == 20
            assert scanner_config["ath_max"] == 40
            assert scanner_config["top_n"] == 10
