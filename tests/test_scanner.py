import pytest
from unittest.mock import Mock, patch
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
    def test_returns_positive_sectors(self, scanner):
        sectors = scanner.get_winning_sectors()
        sector_names = [s["sector"] for s in sectors]
        assert "Technology" in sector_names
        assert "Energy" in sector_names
        assert "Healthcare" not in sector_names

    def test_sorts_by_performance_desc(self, scanner):
        sectors = scanner.get_winning_sectors()
        perfs = [float(s["changesPercentage"]) for s in sectors]
        assert perfs == sorted(perfs, reverse=True)


class TestGetCandidates:
    @patch("scanner.get_stocks_by_sector")
    def test_gets_stocks_from_universe(self, mock_get_stocks, scanner):
        mock_get_stocks.return_value = [
            {"symbol": "AAPL", "name": "Apple", "sector": "Information Technology"}
        ]
        result = scanner.get_candidates(
            [{"sector": "Technology", "changesPercentage": "2.35"}]
        )
        mock_get_stocks.assert_called_once_with("Technology")
        assert len(result) == 1
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["sector_performance"] == 2.35


class TestQuickFilter:
    def test_passes_stock_in_range(self, scanner, mock_client):
        mock_client.get_quote.return_value = {
            "symbol": "AAPL", "price": 150.0, "yearHigh": 200.0,
            "yearLow": 120.0, "volume": 5000000, "averageVolume": 4000000,
            "name": "Apple Inc",
        }
        candidate = {"symbol": "AAPL", "name": "Apple", "sector": "Technology",
                     "sector_performance": 2.35}
        result = scanner.quick_filter(candidate)
        assert result is not None
        assert result["price"] == 150.0

    def test_rejects_stock_near_high(self, scanner, mock_client):
        mock_client.get_quote.return_value = {
            "symbol": "AAPL", "price": 195.0, "yearHigh": 200.0,
            "yearLow": 120.0, "volume": 5000000, "averageVolume": 4000000,
            "name": "Apple Inc",
        }
        candidate = {"symbol": "AAPL", "name": "Apple", "sector": "Technology",
                     "sector_performance": 2.35}
        result = scanner.quick_filter(candidate)
        assert result is None


class TestEnrichCandidate:
    def test_adds_ath_and_score(self, scanner, mock_client):
        mock_client.get_historical_prices.return_value = {
            "symbol": "AAPL",
            "historical": [
                {"high": 180.0}, {"high": 220.0}, {"high": 190.0}
            ]
        }
        candidate = {
            "symbol": "AAPL", "name": "Apple Inc", "sector": "Technology",
            "sector_performance": 2.35, "price": 150.0,
            "yearHigh": 200.0, "yearLow": 120.0,
            "volume": 5000000, "avgVolume": 4000000,
        }
        enriched = scanner.enrich_candidate(candidate)
        assert enriched["ath"] == 220.0
        assert enriched["pct_below_ath"] == pytest.approx(31.8, abs=0.1)
        assert "upside_pct" in enriched
        assert "score" in enriched


class TestRunScan:
    @patch("scanner.get_stocks_by_sector")
    def test_full_pipeline_returns_results(self, mock_get_stocks, scanner, mock_client):
        mock_get_stocks.return_value = [
            {"symbol": "AAPL", "name": "Apple", "sector": "Information Technology"},
        ]
        mock_client.get_quote.return_value = {
            "symbol": "AAPL", "price": 150.0, "yearHigh": 200.0,
            "yearLow": 120.0, "volume": 5000000, "averageVolume": 4000000,
            "name": "Apple Inc",
        }
        mock_client.get_historical_prices.return_value = {
            "symbol": "AAPL",
            "historical": [{"high": 220.0}],
        }

        results = scanner.run_scan()
        assert isinstance(results, dict)
        assert "stocks" in results
        assert "scan_metadata" in results
        assert results["scan_metadata"]["total_candidates"] >= 1
