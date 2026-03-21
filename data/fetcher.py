"""
data/fetcher.py
Handles all yfinance API calls with Streamlit caching.
Returns plain DataFrames/scalars so Streamlit can pickle them safely.
"""

import logging
import streamlit as st
import yfinance as yf
import pandas as pd
from config import CACHE_TTL

logger = logging.getLogger(__name__)


@st.cache_data(ttl=CACHE_TTL)
def get_price(symbol: str) -> float | None:
    """Return the most recent closing price for *symbol*, or None on failure."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d")
        if hist.empty:
            logger.warning("Empty price history for %s", symbol)
            return None
        return float(hist.iloc[-1]["Close"])
    except Exception as exc:
        logger.error("Failed to fetch price for %s: %s", symbol, exc)
        return None


@st.cache_data(ttl=CACHE_TTL)
def get_expirations(symbol: str) -> tuple[str, ...]:
    """Return available option expiration dates for *symbol*.

    Returns an empty tuple when the ticker has no listed options.
    """
    try:
        ticker = yf.Ticker(symbol)
        exps = ticker.options
        return tuple(exps) if exps else ()
    except Exception as exc:
        logger.error("Failed to fetch expirations for %s: %s", symbol, exc)
        return ()


@st.cache_data(ttl=CACHE_TTL)
def get_option_chain(symbol: str, date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (calls_df, puts_df) for *symbol* expiring on *date*.

    Both DataFrames may be empty on failure.
    """
    empty = pd.DataFrame()
    try:
        ticker = yf.Ticker(symbol)
        chain = ticker.option_chain(date)
        calls = chain.calls.copy()
        puts = chain.puts.copy()
        # Ensure numeric columns are clean
        for df in (calls, puts):
            for col in ("openInterest", "volume", "impliedVolatility", "lastPrice", "bid", "ask", "strike"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        return calls, puts
    except Exception as exc:
        logger.error("Failed to fetch option chain for %s/%s: %s", symbol, date, exc)
        return empty, empty
