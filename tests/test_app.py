import pytest
import json
import os
from unittest.mock import patch, Mock
from app import create_app


@pytest.fixture
def app_client():
    app = create_app(testing=True)
    with app.test_client() as c:
        yield c, app


class TestIndexRoute:
    def test_serves_html(self, app_client):
        client, _ = app_client
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"Swing Trade Scanner" in resp.data


class TestScanRoute:
    def test_returns_scan_results(self, app_client):
        client, _ = app_client
        with patch.dict(os.environ, {"FMP_API_KEY": "test_key"}), \
             patch("app.FMPClient") as mock_fmp_cls, \
             patch("app.Scanner") as mock_scanner_cls, \
             patch("app._save_report"):
            mock_scanner = Mock()
            mock_scanner.run_scan.return_value = {
                "stocks": [{"symbol": "AAPL", "score": 75.0, "rank": 1}],
                "scan_metadata": {"total_candidates": 50},
            }
            mock_scanner_cls.return_value = mock_scanner

            resp = client.post("/api/scan")
            assert resp.status_code == 200
            data = json.loads(resp.data)
            assert "stocks" in data
            assert len(data["stocks"]) == 1

    def test_returns_error_without_api_key(self, app_client, monkeypatch):
        client, _ = app_client
        monkeypatch.delenv("FMP_API_KEY", raising=False)
        resp = client.post("/api/scan")
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data


class TestCSVRoute:
    def test_returns_error_without_scan_data(self, app_client):
        client, _ = app_client
        resp = client.get("/api/csv")
        assert resp.status_code == 400

    def test_returns_csv_after_scan(self, app_client):
        client, _ = app_client
        with patch.dict(os.environ, {"FMP_API_KEY": "test_key"}), \
             patch("app.FMPClient"), \
             patch("app.Scanner") as mock_scanner_cls, \
             patch("app._save_report"):
            mock_scanner = Mock()
            mock_scanner.run_scan.return_value = {
                "stocks": [{
                    "rank": 1, "symbol": "AAPL", "name": "Apple",
                    "sector": "Technology", "sector_performance": 2.35,
                    "price": 150.0, "yearHigh": 200.0, "ath": 220.0,
                    "pct_below_ath": 31.8, "target_price": 220.0,
                    "upside_pct": 46.7, "score": 75.0,
                }],
                "scan_metadata": {"total_candidates": 50},
            }
            mock_scanner_cls.return_value = mock_scanner

            # Run scan first
            client.post("/api/scan")

            # Then download CSV
            resp = client.get("/api/csv")
            assert resp.status_code == 200
            assert resp.content_type == "text/csv; charset=utf-8"
            assert b"AAPL" in resp.data
