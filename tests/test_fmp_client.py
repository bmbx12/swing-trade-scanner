import pytest
from unittest.mock import patch, Mock
from fmp_client import FMPClient, BudgetExhausted


@pytest.fixture
def client():
    return FMPClient(api_key="test_key")


class TestFMPClientInit:
    def test_stores_api_key(self, client):
        assert client.api_key == "test_key"

    def test_base_url(self, client):
        assert client.base_url == "https://financialmodelingprep.com/stable"

    def test_default_call_budget(self, client):
        assert client.call_budget == 200

    def test_custom_call_budget(self):
        c = FMPClient(api_key="test_key", call_budget=50)
        assert c.call_budget == 50

    def test_calls_made_starts_at_zero(self, client):
        assert client.calls_made == 0


class TestCallBudget:
    @patch("fmp_client.requests.get")
    def test_tracks_calls_made(self, mock_get, client):
        mock_get.return_value = Mock(
            status_code=200, json=Mock(return_value=[{"symbol": "AAPL"}])
        )
        client.get_quote("AAPL")
        assert client.calls_made == 1
        client.get_quote("MSFT")
        assert client.calls_made == 2

    def test_raises_budget_exhausted_when_limit_reached(self):
        c = FMPClient(api_key="test_key", call_budget=0)
        with pytest.raises(BudgetExhausted, match="budget of 0 reached"):
            c.get_quote("AAPL")

    @patch("fmp_client.requests.get")
    def test_429_raises_budget_exhausted(self, mock_get, client):
        mock_get.return_value = Mock(
            status_code=429, text="Limit Reach"
        )
        with pytest.raises(BudgetExhausted, match="rate limit"):
            client.get_quote("AAPL")


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
        call_args = mock_get.call_args
        assert call_args[1]["params"]["symbol"] == "AAPL"


class TestGetHistoricalPrices:
    @patch("fmp_client.requests.get")
    def test_returns_historical_data_from_list(self, mock_get, client):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value=[
                {"date": "2026-02-20", "high": 180.0, "symbol": "AAPL"},
                {"date": "2025-06-15", "high": 220.0, "symbol": "AAPL"},
            ])
        )
        result = client.get_historical_prices("AAPL")
        assert result["symbol"] == "AAPL"
        assert len(result["historical"]) == 2

    @patch("fmp_client.requests.get")
    def test_default_timeseries_is_5_years(self, mock_get, client):
        mock_get.return_value = Mock(
            status_code=200, json=Mock(return_value=[])
        )
        client.get_historical_prices("AAPL")
        call_args = mock_get.call_args
        assert call_args[1]["params"]["timeseries"] == 1260

    @patch("fmp_client.requests.get")
    def test_returns_dict_format_unchanged(self, mock_get, client):
        mock_get.return_value = Mock(
            status_code=200,
            json=Mock(return_value={
                "symbol": "AAPL",
                "historical": [{"high": 200.0}]
            })
        )
        result = client.get_historical_prices("AAPL")
        assert result["symbol"] == "AAPL"
        assert len(result["historical"]) == 1
