"""
core/calculations.py
Pure financial calculations — no Streamlit or UI dependencies.
All functions accept DataFrames / scalars and return plain Python types or DataFrames.
"""

import math
import logging
import numpy as np
import pandas as pd
from scipy.stats import norm
from datetime import date as dt_date

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------

def calc_pc_ratio(calls_df: pd.DataFrame, puts_df: pd.DataFrame) -> float:
    """Put/Call ratio based on total open interest across the full chain."""
    total_call_oi = calls_df["openInterest"].sum()
    total_put_oi = puts_df["openInterest"].sum()
    if total_call_oi <= 0:
        return 0.0
    return float(total_put_oi / total_call_oi)


# ---------------------------------------------------------------------------
# Max Pain
# ---------------------------------------------------------------------------

def calc_max_pain(calls_df: pd.DataFrame, puts_df: pd.DataFrame) -> float:
    """Calculate Max Pain strike price.

    Max Pain = strike at which total option payout to holders is minimised,
    i.e. the price that causes the most options to expire worthless.

    Algorithm:
        For each candidate strike K:
            pain = sum over all call strikes k  : max(0, k - K) * call_OI(k) * 100
                 + sum over all put strikes k   : max(0, K - k) * put_OI(k)  * 100
        Return K that minimises pain.
    """
    call_strikes = calls_df["strike"].tolist() if "strike" in calls_df.columns else []
    put_strikes = puts_df["strike"].tolist() if "strike" in puts_df.columns else []
    all_strikes = sorted(set(call_strikes + put_strikes))
    if not all_strikes:
        return 0.0

    call_oi = calls_df.set_index("strike")["openInterest"] if "strike" in calls_df.columns else pd.Series(dtype=float)
    put_oi = puts_df.set_index("strike")["openInterest"] if "strike" in puts_df.columns else pd.Series(dtype=float)

    min_pain = float("inf")
    max_pain_strike = all_strikes[0]

    for K in all_strikes:
        call_pain = sum(
            max(0.0, k - K) * call_oi.get(k, 0)
            for k in all_strikes
        )
        put_pain = sum(
            max(0.0, K - k) * put_oi.get(k, 0)
            for k in all_strikes
        )
        total = (call_pain + put_pain) * 100
        if total < min_pain:
            min_pain = total
            max_pain_strike = K

    return float(max_pain_strike)


# ---------------------------------------------------------------------------
# Black-Scholes
# ---------------------------------------------------------------------------

def _time_to_expiry(expiry_date_str: str) -> float:
    """Return years remaining until *expiry_date_str* (YYYY-MM-DD)."""
    try:
        expiry = dt_date.fromisoformat(expiry_date_str)
        today = dt_date.today()
        days = (expiry - today).days
        return max(days / 365.0, 1 / 365.0)   # floor at 1 day
    except Exception:
        return 30 / 365.0


def calc_black_scholes(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = "call",
) -> float:
    """Return the Black-Scholes theoretical price.

    Args:
        S: Current stock price
        K: Strike price
        T: Time to expiry in years
        r: Risk-free rate (annualized)
        sigma: Implied volatility (annualized, decimal)
        option_type: 'call' or 'put'
    """
    if sigma <= 0 or T <= 0 or S <= 0 or K <= 0:
        return 0.0
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        if option_type == "call":
            return float(S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2))
        else:
            return float(K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))
    except Exception as exc:
        logger.warning("Black-Scholes failed (S=%s K=%s T=%s sigma=%s): %s", S, K, T, sigma, exc)
        return 0.0


def calc_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = "call",
) -> dict:
    """Return delta, gamma, theta, vega for one option contract.

    Theta is expressed as daily decay (divided by 365).
    Vega is expressed per 1% change in IV.
    """
    if sigma <= 0 or T <= 0 or S <= 0 or K <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    try:
        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        pdf_d1 = norm.pdf(d1)
        sqrt_T = math.sqrt(T)

        gamma = pdf_d1 / (S * sigma * sqrt_T)
        vega = S * pdf_d1 * sqrt_T / 100          # per 1% IV move
        if option_type == "call":
            delta = norm.cdf(d1)
            theta = (
                -(S * pdf_d1 * sigma) / (2 * sqrt_T)
                - r * K * math.exp(-r * T) * norm.cdf(d2)
            ) / 365
        else:
            delta = norm.cdf(d1) - 1
            theta = (
                -(S * pdf_d1 * sigma) / (2 * sqrt_T)
                + r * K * math.exp(-r * T) * norm.cdf(-d2)
            ) / 365
        return {
            "delta": round(delta, 4),
            "gamma": round(gamma, 4),
            "theta": round(theta, 4),
            "vega": round(vega, 4),
        }
    except Exception as exc:
        logger.warning("Greeks failed: %s", exc)
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}


def add_theoretical_prices(
    df: pd.DataFrame,
    current_price: float,
    expiry_date_str: float,
    r: float,
    option_type: str = "call",
) -> pd.DataFrame:
    """Append BS_Price, delta, gamma, theta, vega columns to *df* in-place (copy).

    Uses the impliedVolatility already in the DataFrame as sigma.
    """
    out = df.copy()
    T = _time_to_expiry(expiry_date_str)

    def _row(row):
        sigma = row.get("impliedVolatility", 0)
        K = row.get("strike", 0)
        bs = calc_black_scholes(current_price, K, T, r, sigma, option_type)
        greeks = calc_greeks(current_price, K, T, r, sigma, option_type)
        return pd.Series({
            "BS_Price": round(bs, 4),
            "delta": greeks["delta"],
            "gamma": greeks["gamma"],
            "theta": greeks["theta"],
            "vega": greeks["vega"],
        })

    extras = out.apply(_row, axis=1)
    return pd.concat([out, extras], axis=1)


# ---------------------------------------------------------------------------
# Hedging
# ---------------------------------------------------------------------------

def calc_hedging_cost(shares: int, put_price: float) -> tuple[float, float]:
    """Return (contracts_needed, total_cost_usd)."""
    contracts = shares / 100.0
    cost = put_price * 100 * contracts
    return contracts, cost
