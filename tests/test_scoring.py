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
        assert calculate_pct_below_ath(80.0, 100.0) == pytest.approx(20.0)

    def test_at_ath(self):
        assert calculate_pct_below_ath(100.0, 100.0) == pytest.approx(0.0)

    def test_50_pct_below(self):
        assert calculate_pct_below_ath(50.0, 100.0) == pytest.approx(50.0)


class TestCalculateUpside:
    def test_basic_upside(self):
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
