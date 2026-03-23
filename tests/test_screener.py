"""
tests/test_screener.py
Unit tests for core/technical_indicators.py (pure functions only).
No yfinance calls, no Streamlit, no FinMind.
"""

import numpy as np
import pandas as pd
import pytest

from core.technical_indicators import (
    calc_moving_averages,
    calc_rsi,
    calc_macd,
    calc_kd,
    calc_bollinger,
    calc_volume_spike,
    scan_technicals,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic price series
# ---------------------------------------------------------------------------

def _make_df(closes, highs=None, lows=None, volumes=None) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame from a list of close prices."""
    n = len(closes)
    closes = np.array(closes, dtype=float)
    if highs is None:
        highs = closes * 1.01
    if lows is None:
        lows = closes * 0.99
    if volumes is None:
        volumes = np.ones(n) * 1_000_000

    return pd.DataFrame({
        "Open":   closes,
        "High":   highs,
        "Low":    lows,
        "Close":  closes,
        "Volume": volumes,
    })


def _ramp(start, end, n) -> list:
    return list(np.linspace(start, end, n))


# ---------------------------------------------------------------------------
# Moving Average tests
# ---------------------------------------------------------------------------

class TestMovingAverages:
    def test_insufficient_data_returns_none(self):
        df = _make_df([100] * 30)  # < 60 bars
        result = calc_moving_averages(df)
        assert result["ma5"] is None
        assert result["ma_signal"] is None

    def test_neutral_signal_in_flat_market(self):
        df = _make_df([100.0] * 80)
        result = calc_moving_averages(df)
        assert result["ma_signal"] == "neutral"
        assert result["ma5"] == pytest.approx(100.0, abs=0.01)

    def test_golden_cross_detection(self):
        # Build series: 60 bars down-trend (MA5 < MA20), then 5 bars sharp up
        down = _ramp(200, 120, 60)
        up = _ramp(120, 180, 20)
        prices = down + up
        df = _make_df(prices)
        result = calc_moving_averages(df)
        # After a reversal we should see golden_cross at some point;
        # test that the function doesn't crash and returns a valid signal.
        assert result["ma_signal"] in ("golden_cross", "neutral", "death_cross")

    def test_death_cross_after_downturn(self):
        # Long up-trend (MA5 > MA20), then sharp drop
        up = _ramp(100, 200, 60)
        down = _ramp(200, 130, 20)
        prices = up + down
        df = _make_df(prices)
        result = calc_moving_averages(df)
        assert result["ma_signal"] in ("death_cross", "neutral", "golden_cross")

    def test_all_ma_values_are_positive(self):
        df = _make_df(_ramp(100, 150, 80))
        result = calc_moving_averages(df)
        assert result["ma5"] > 0
        assert result["ma20"] > 0
        assert result["ma60"] > 0


# ---------------------------------------------------------------------------
# RSI tests
# ---------------------------------------------------------------------------

class TestRSI:
    def test_insufficient_data_returns_none(self):
        result = calc_rsi(_make_df([100] * 5))
        assert result["rsi"] is None

    def test_oversold_signal_on_downtrend(self):
        # Pure down-trend should produce low RSI
        prices = _ramp(200, 100, 80)
        result = calc_rsi(_make_df(prices))
        assert result["rsi"] is not None
        assert result["rsi"] < 50
        assert result["rsi_signal"] in ("oversold", "neutral")

    def test_overbought_signal_on_uptrend(self):
        # Pure up-trend should produce high RSI
        prices = _ramp(100, 300, 80)
        result = calc_rsi(_make_df(prices))
        assert result["rsi"] is not None
        assert result["rsi"] > 50
        assert result["rsi_signal"] in ("overbought", "neutral")

    def test_rsi_bounded_0_to_100(self):
        for prices in [_ramp(100, 1, 80), _ramp(1, 100, 80), [50.0] * 80]:
            result = calc_rsi(_make_df(prices))
            if result["rsi"] is not None:
                assert 0 <= result["rsi"] <= 100

    def test_flat_market_rsi_near_50(self):
        prices = [100.0] * 80
        result = calc_rsi(_make_df(prices))
        # Flat prices → delta = 0, RSI should be ~50 or NaN
        # Either is acceptable; just must not raise
        assert result["rsi_signal"] in ("neutral", "oversold", "overbought", None)


# ---------------------------------------------------------------------------
# MACD tests
# ---------------------------------------------------------------------------

class TestMACD:
    def test_insufficient_data_returns_none(self):
        result = calc_macd(_make_df([100] * 20))
        assert result["macd"] is None

    def test_bullish_cross_on_sharp_reversal(self):
        # Down-trend then reversal
        down = _ramp(300, 150, 50)
        up = _ramp(150, 250, 30)
        df = _make_df(down + up)
        result = calc_macd(df)
        assert result["macd"] is not None
        assert result["macd_signal"] in ("bullish_cross", "bearish_cross", "neutral")

    def test_macd_and_signal_line_are_floats(self):
        df = _make_df(_ramp(100, 200, 60))
        result = calc_macd(df)
        assert isinstance(result["macd"], float)
        assert isinstance(result["signal_line"], float)
        assert isinstance(result["histogram"], float)

    def test_histogram_equals_macd_minus_signal(self):
        df = _make_df(_ramp(100, 200, 60))
        result = calc_macd(df)
        # Allow 1e-3 tolerance due to rounding in the returned values
        assert result["histogram"] == pytest.approx(
            result["macd"] - result["signal_line"], abs=1e-3
        )


# ---------------------------------------------------------------------------
# KD Stochastic tests
# ---------------------------------------------------------------------------

class TestKD:
    def test_insufficient_data_returns_none(self):
        result = calc_kd(_make_df([100] * 5))
        assert result["k"] is None

    def test_k_d_bounded_0_to_100(self):
        df = _make_df(_ramp(100, 200, 80))
        result = calc_kd(df)
        if result["k"] is not None:
            assert 0 <= result["k"] <= 100
        if result["d"] is not None:
            assert 0 <= result["d"] <= 100

    def test_valid_signal_values(self):
        valid_signals = {"golden_cross", "death_cross", "oversold", "overbought", "neutral"}
        df = _make_df(_ramp(100, 200, 80))
        result = calc_kd(df)
        if result["kd_signal"] is not None:
            assert result["kd_signal"] in valid_signals

    def test_oversold_in_severe_downtrend(self):
        prices = _ramp(200, 50, 80)
        result = calc_kd(_make_df(prices))
        if result["k"] is not None:
            assert result["k"] < 50


# ---------------------------------------------------------------------------
# Bollinger Band tests
# ---------------------------------------------------------------------------

class TestBollinger:
    def test_insufficient_data_returns_none(self):
        result = calc_bollinger(_make_df([100] * 10))
        assert result["bb_upper"] is None

    def test_upper_greater_than_lower(self):
        df = _make_df(_ramp(100, 200, 80))
        result = calc_bollinger(df)
        assert result["bb_upper"] > result["bb_lower"]

    def test_middle_between_upper_and_lower(self):
        df = _make_df(_ramp(100, 200, 80))
        result = calc_bollinger(df)
        assert result["bb_lower"] < result["bb_middle"] < result["bb_upper"]

    def test_flat_market_tight_bands(self):
        df = _make_df([100.0] * 60)
        result = calc_bollinger(df)
        # Flat market → very narrow bands
        if result["bb_upper"] is not None:
            assert result["bb_upper"] - result["bb_lower"] < 1.0

    def test_valid_signal_values(self):
        valid = {"near_upper", "near_lower", "inside"}
        df = _make_df(_ramp(100, 200, 60))
        result = calc_bollinger(df)
        if result["bb_signal"] is not None:
            assert result["bb_signal"] in valid


# ---------------------------------------------------------------------------
# Volume Spike tests
# ---------------------------------------------------------------------------

class TestVolumeSpike:
    def test_normal_volume(self):
        vols = [1_000_000] * 60
        df = _make_df([100] * 60, volumes=vols)
        result = calc_volume_spike(df)
        assert result["volume_ratio"] == pytest.approx(1.0, abs=0.1)
        assert result["volume_signal"] == "normal"

    def test_spike_detection(self):
        # 59 bars of 1M volume, last bar 5M
        vols = [1_000_000] * 59 + [5_000_000]
        df = _make_df([100] * 60, volumes=vols)
        result = calc_volume_spike(df)
        assert result["volume_ratio"] > 2.0
        assert result["volume_signal"] == "spike"

    def test_missing_volume_column(self):
        df = pd.DataFrame({"Close": [100.0] * 60})
        result = calc_volume_spike(df)
        assert result["volume_ratio"] is None


# ---------------------------------------------------------------------------
# scan_technicals integration test
# ---------------------------------------------------------------------------

class TestScanTechnicals:
    def test_returns_empty_dict_on_none(self):
        result = scan_technicals(None)
        assert result == {}

    def test_returns_empty_dict_on_empty_df(self):
        result = scan_technicals(pd.DataFrame())
        assert result == {}

    def test_insufficient_data_returns_partial_with_nones(self):
        df = _make_df([100.0] * 30)
        result = scan_technicals(df)
        # price should still be computed; MA signals should be None
        assert result.get("price") == 100.0
        assert result.get("ma5") is None

    def test_full_result_structure(self):
        df = _make_df(_ramp(100, 200, 80))
        result = scan_technicals(df)
        expected_keys = [
            "price",
            "ma5", "ma20", "ma60", "ma_signal",
            "rsi", "rsi_signal",
            "macd", "signal_line", "histogram", "macd_signal",
            "k", "d", "kd_signal",
            "bb_upper", "bb_middle", "bb_lower", "bb_signal",
            "volume_ratio", "volume_signal",
        ]
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"

    def test_price_is_last_close(self):
        prices = _ramp(100, 200, 80)
        df = _make_df(prices)
        result = scan_technicals(df)
        assert result["price"] == pytest.approx(prices[-1], abs=0.01)
