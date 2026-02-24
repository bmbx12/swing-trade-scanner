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
