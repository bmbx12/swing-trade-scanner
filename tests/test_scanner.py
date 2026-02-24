import pytest
from unittest.mock import Mock
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
