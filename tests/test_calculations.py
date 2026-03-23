"""
tests/test_calculations.py
Unit tests for core/calculations.py
Run with:  pytest tests/
"""

import math
import pytest
import pandas as pd

from core.calculations import (
    calc_pc_ratio,
    calc_max_pain,
    calc_black_scholes,
    calc_greeks,
    calc_hedging_cost,
    add_theoretical_prices,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_calls(data: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(data)


def make_puts(data: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(data)


# ---------------------------------------------------------------------------
# P/C Ratio
# ---------------------------------------------------------------------------

class TestCalcPcRatio:
    def test_basic(self):
        calls = make_calls([{"openInterest": 1000}])
        puts = make_puts([{"openInterest": 1500}])
        assert calc_pc_ratio(calls, puts) == pytest.approx(1.5)

    def test_zero_calls(self):
        """Should return 0 when call OI is zero (no division by zero)."""
        calls = make_calls([{"openInterest": 0}])
        puts = make_puts([{"openInterest": 500}])
        assert calc_pc_ratio(calls, puts) == 0.0

    def test_bullish_ratio(self):
        calls = make_calls([{"openInterest": 2000}])
        puts = make_puts([{"openInterest": 800}])
        assert calc_pc_ratio(calls, puts) == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# Max Pain
# ---------------------------------------------------------------------------

class TestCalcMaxPain:
    def test_single_strike(self):
        calls = make_calls([{"strike": 100, "openInterest": 100}])
        puts = make_puts([{"strike": 100, "openInterest": 100}])
        result = calc_max_pain(calls, puts)
        assert result == 100.0

    def test_empty_frames(self):
        calls = make_calls([])
        puts = make_puts([])
        # Should not raise; returns 0 or first element
        result = calc_max_pain(calls, puts)
        assert isinstance(result, float)

    def test_known_max_pain(self):
        """
        Scenario:
          Calls at 95 (OI=500), 100 (OI=200)
          Puts  at 95 (OI=100), 100 (OI=600)

        At expiry=95:  call pain = 0+0=0,  put pain = 0+5*600=3000  → total=3000
        At expiry=100: call pain = 5*500+0=2500, put pain = 0        → total=2500
        Max pain = 100 (minimises total payout)
        """
        calls = make_calls([
            {"strike": 95, "openInterest": 500},
            {"strike": 100, "openInterest": 200},
        ])
        puts = make_puts([
            {"strike": 95, "openInterest": 100},
            {"strike": 100, "openInterest": 600},
        ])
        assert calc_max_pain(calls, puts) == 100.0


# ---------------------------------------------------------------------------
# Black-Scholes
# ---------------------------------------------------------------------------

class TestCalcBlackScholes:
    def test_call_positive(self):
        price = calc_black_scholes(S=100, K=100, T=1, r=0.05, sigma=0.2, option_type="call")
        assert price > 0

    def test_put_positive(self):
        price = calc_black_scholes(S=100, K=100, T=1, r=0.05, sigma=0.2, option_type="put")
        assert price > 0

    def test_put_call_parity(self):
        """C - P = S - K*e^(-rT)"""
        S, K, T, r, sigma = 100, 100, 1, 0.05, 0.2
        call = calc_black_scholes(S, K, T, r, sigma, "call")
        put = calc_black_scholes(S, K, T, r, sigma, "put")
        expected = S - K * math.exp(-r * T)
        assert abs((call - put) - expected) < 0.01

    def test_zero_sigma_returns_zero(self):
        price = calc_black_scholes(S=100, K=100, T=1, r=0.05, sigma=0, option_type="call")
        assert price == 0.0

    def test_deep_itm_call(self):
        """Deep ITM call should be close to intrinsic value S - K."""
        price = calc_black_scholes(S=200, K=100, T=0.01, r=0.05, sigma=0.01, option_type="call")
        assert price == pytest.approx(100, abs=2)


# ---------------------------------------------------------------------------
# Greeks
# ---------------------------------------------------------------------------

class TestCalcGreeks:
    def test_call_delta_bounds(self):
        greeks = calc_greeks(S=100, K=100, T=1, r=0.05, sigma=0.2, option_type="call")
        assert 0.0 <= greeks["delta"] <= 1.0

    def test_put_delta_bounds(self):
        greeks = calc_greeks(S=100, K=100, T=1, r=0.05, sigma=0.2, option_type="put")
        assert -1.0 <= greeks["delta"] <= 0.0

    def test_gamma_positive(self):
        greeks = calc_greeks(S=100, K=100, T=1, r=0.05, sigma=0.2, option_type="call")
        assert greeks["gamma"] >= 0

    def test_theta_negative_call(self):
        """Theta should be negative (time decay costs the holder)."""
        greeks = calc_greeks(S=100, K=100, T=1, r=0.05, sigma=0.2, option_type="call")
        assert greeks["theta"] < 0

    def test_vega_positive(self):
        greeks = calc_greeks(S=100, K=100, T=1, r=0.05, sigma=0.2, option_type="call")
        assert greeks["vega"] > 0

    def test_zero_sigma_safe(self):
        greeks = calc_greeks(S=100, K=100, T=1, r=0.05, sigma=0, option_type="call")
        assert greeks == {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}


# ---------------------------------------------------------------------------
# Hedging Cost
# ---------------------------------------------------------------------------

class TestCalcHedgingCost:
    def test_100_shares(self):
        contracts, cost = calc_hedging_cost(shares=100, put_price=3.50)
        assert contracts == 1.0
        assert cost == pytest.approx(350.0)

    def test_250_shares(self):
        contracts, cost = calc_hedging_cost(shares=250, put_price=2.0)
        assert contracts == 2.5
        assert cost == pytest.approx(500.0)


# ---------------------------------------------------------------------------
# add_theoretical_prices
# ---------------------------------------------------------------------------

class TestAddTheoreticalPrices:
    def _sample_df(self):
        return pd.DataFrame([
            {"strike": 95, "lastPrice": 6.0, "impliedVolatility": 0.25},
            {"strike": 100, "lastPrice": 3.5, "impliedVolatility": 0.22},
            {"strike": 105, "lastPrice": 1.5, "impliedVolatility": 0.20},
        ])

    def test_columns_added(self):
        df = add_theoretical_prices(
            self._sample_df(), current_price=100, expiry_date_str="2026-06-20",
            r=0.05, option_type="call"
        )
        assert "BS_Price" in df.columns
        assert "delta" in df.columns

    def test_bs_price_positive(self):
        df = add_theoretical_prices(
            self._sample_df(), current_price=100, expiry_date_str="2026-06-20",
            r=0.05, option_type="call"
        )
        assert (df["BS_Price"] >= 0).all()

    def test_original_rows_preserved(self):
        original = self._sample_df()
        df = add_theoretical_prices(
            original, current_price=100, expiry_date_str="2026-06-20",
            r=0.05, option_type="call"
        )
        assert len(df) == len(original)
