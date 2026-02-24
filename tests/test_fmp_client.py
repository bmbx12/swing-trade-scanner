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
        assert client.base_url == "https://financialmodelingprep.com/stable"


class TestGetSectorPerformance:
    @patch("fmp_client.requests.get")
    def test_returns_aggregated_sector_data(self, mock_get, client):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value=[
                {"sector": "Technology", "exchange": "NASDAQ", "averageChange": 2.5},
                {"sector": "Technology", "exchange": "NYSE", "averageChange": 1.5},
                {"sector": "Energy", "exchange": "NASDAQ", "averageChange": 1.0},
                {"sector": "Energy", "exchange": "NYSE", "averageChange": 1.2},
            ])
        )
        result = client.get_sector_performance(date="2026-02-20")
        assert len(result) == 2
        # Technology should average 2.0
        tech = next(s for s in result if s["sector"] == "Technology")
        assert float(tech["changesPercentage"]) == pytest.approx(2.0)

    @patch("fmp_client.requests.get")
    def test_handles_api_error(self, mock_get, client):
        mock_get.return_value = Mock(status_code=401, text="Unauthorized")
        with pytest.raises(Exception, match="FMP API error 401"):
            client.get_sector_performance(date="2026-02-20")


class TestGetQuote:
    @patch("fmp_client.requests.get")
    def test_returns_quote_data(self, mock_get, client):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value=[{
                "symbol": "AAPL", "price": 180.0, "yearHigh": 200.0,
                "yearLow": 140.0, "volume": 50000000, "averageVolume": 45000000,
                "name": "Apple Inc",
            }])
        )
        result = client.get_quote("AAPL")
        assert result["symbol"] == "AAPL"
        assert result["price"] == 180.0
        # Verify uses symbol param, not URL path
        call_args = mock_get.call_args
        assert call_args[1]["params"]["symbol"] == "AAPL"


class TestGetHistoricalPrices:
    @patch("fmp_client.requests.get")
    def test_returns_historical_data_from_list(self, mock_get, client):
        """New stable API returns flat list, client wraps it."""
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value=[
                {"date": "2026-02-20", "high": 180.0, "symbol": "AAPL"},
                {"date": "2025-06-15", "high": 220.0, "symbol": "AAPL"},
            ])
        )
        result = client.get_historical_prices("AAPL", timeseries=365)
        assert result["symbol"] == "AAPL"
        assert len(result["historical"]) == 2

    @patch("fmp_client.requests.get")
    def test_returns_dict_format_unchanged(self, mock_get, client):
        """If API returns dict format, pass through."""
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "symbol": "AAPL",
                "historical": [{"high": 200.0}]
            })
        )
        result = client.get_historical_prices("AAPL", timeseries=365)
        assert result["symbol"] == "AAPL"
        assert len(result["historical"]) == 1
