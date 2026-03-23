"""
core/technical_indicators.py
Pure functions for computing technical indicators from OHLCV DataFrames.
No UI, no external API calls.
Input: pd.DataFrame with columns [Open, High, Low, Close, Volume] from yfinance.
"""

import logging

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)

# Minimum bars needed for MA60 to be valid
MIN_BARS = 60


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calc_moving_averages(df: pd.DataFrame) -> dict:
    """
    Returns MA5/MA20/MA60 and golden/death cross signal.
    Golden cross: MA5 crosses above MA20 (yesterday below, today above).
    Death cross: MA5 crosses below MA20.
    """
    if df is None or len(df) < MIN_BARS:
        return {"ma5": None, "ma20": None, "ma60": None, "ma_signal": None}

    close = df["Close"].squeeze()
    ma5 = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    signal = "neutral"
    if len(ma5) >= 2 and not pd.isna(ma5.iloc[-2]) and not pd.isna(ma20.iloc[-2]):
        prev_diff = float(ma5.iloc[-2]) - float(ma20.iloc[-2])
        curr_diff = float(ma5.iloc[-1]) - float(ma20.iloc[-1])
        if prev_diff < 0 and curr_diff >= 0:
            signal = "golden_cross"
        elif prev_diff > 0 and curr_diff <= 0:
            signal = "death_cross"

    def _safe(s):
        v = s.iloc[-1]
        return round(float(v), 2) if not pd.isna(v) else None

    return {
        "ma5": _safe(ma5),
        "ma20": _safe(ma20),
        "ma60": _safe(ma60),
        "ma_signal": signal,
    }


def calc_rsi(df: pd.DataFrame, period: int = 14) -> dict:
    """
    RSI(14) using Wilder's EMA smoothing.
    Returns rsi value and oversold/overbought/neutral signal.
    """
    if df is None or len(df) < period + 1:
        return {"rsi": None, "rsi_signal": None}

    close = df["Close"].squeeze()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    # When loss is 0 (pure uptrend), RSI = 100
    rsi_series = np.where(
        loss == 0,
        100.0,
        100 - (100 / (1 + gain / loss.replace(0, np.nan)))
    )
    rsi_series = pd.Series(rsi_series, index=close.index)
    rsi_val = float(rsi_series.iloc[-1])

    if pd.isna(rsi_val):
        return {"rsi": None, "rsi_signal": None}

    if rsi_val < config.RSI_OVERSOLD:
        signal = "oversold"
    elif rsi_val > config.RSI_OVERBOUGHT:
        signal = "overbought"
    else:
        signal = "neutral"

    return {"rsi": round(rsi_val, 1), "rsi_signal": signal}


def calc_macd(df: pd.DataFrame) -> dict:
    """
    MACD (12, 26, 9).
    Returns macd line, signal line, histogram, and cross signal.
    """
    if df is None or len(df) < 35:
        return {"macd": None, "signal_line": None, "histogram": None, "macd_signal": None}

    close = df["Close"].squeeze()
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    macd_line = ema12 - ema26
    sig_line = _ema(macd_line, 9)
    hist = macd_line - sig_line

    signal = "neutral"
    if len(macd_line) >= 2:
        prev_diff = float(macd_line.iloc[-2]) - float(sig_line.iloc[-2])
        curr_diff = float(macd_line.iloc[-1]) - float(sig_line.iloc[-1])
        if prev_diff < 0 and curr_diff >= 0:
            signal = "bullish_cross"
        elif prev_diff > 0 and curr_diff <= 0:
            signal = "bearish_cross"

    return {
        "macd": round(float(macd_line.iloc[-1]), 4),
        "signal_line": round(float(sig_line.iloc[-1]), 4),
        "histogram": round(float(hist.iloc[-1]), 4),
        "macd_signal": signal,
    }


def calc_kd(df: pd.DataFrame, period: int = 9) -> dict:
    """
    KD Stochastic oscillator (period=9, 1/3 smoothing).
    Returns K, D values and golden/death cross or oversold/overbought signal.
    """
    if df is None or len(df) < period + 3:
        return {"k": None, "d": None, "kd_signal": None}

    high = df["High"].squeeze()
    low = df["Low"].squeeze()
    close = df["Close"].squeeze()

    lowest_low = low.rolling(period).min()
    highest_high = high.rolling(period).max()
    denom = (highest_high - lowest_low).replace(0, np.nan)
    rsv = (close - lowest_low) / denom * 100

    # com=2 gives 1/3 weight to new data (same as traditional KD)
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()

    k_val = float(k.iloc[-1])
    d_val = float(d.iloc[-1])

    if pd.isna(k_val) or pd.isna(d_val):
        return {"k": None, "d": None, "kd_signal": None}

    signal = "neutral"
    if len(k) >= 2 and not pd.isna(k.iloc[-2]) and not pd.isna(d.iloc[-2]):
        prev_diff = float(k.iloc[-2]) - float(d.iloc[-2])
        curr_diff = k_val - d_val
        if prev_diff < 0 and curr_diff >= 0:
            signal = "golden_cross"
        elif prev_diff > 0 and curr_diff <= 0:
            signal = "death_cross"
        elif k_val < config.KD_OVERSOLD:
            signal = "oversold"
        elif k_val > config.KD_OVERBOUGHT:
            signal = "overbought"

    return {"k": round(k_val, 1), "d": round(d_val, 1), "kd_signal": signal}


def calc_bollinger(df: pd.DataFrame, period: int = 20, std_dev: float = 2.0) -> dict:
    """
    Bollinger Bands (20, 2).
    Returns upper/middle/lower and near_upper/near_lower/inside signal.
    """
    if df is None or len(df) < period:
        return {"bb_upper": None, "bb_middle": None, "bb_lower": None, "bb_signal": None}

    close = df["Close"].squeeze()
    middle = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std

    price = float(close.iloc[-1])
    upper_val = float(upper.iloc[-1])
    lower_val = float(lower.iloc[-1])
    middle_val = float(middle.iloc[-1])

    band_width = upper_val - lower_val
    signal = "inside"
    if band_width > 0:
        pct_b = (price - lower_val) / band_width
        if pct_b > 0.95:
            signal = "near_upper"
        elif pct_b < 0.05:
            signal = "near_lower"

    return {
        "bb_upper": round(upper_val, 2),
        "bb_middle": round(middle_val, 2),
        "bb_lower": round(lower_val, 2),
        "bb_signal": signal,
    }


def calc_volume_spike(df: pd.DataFrame, period: int = 20) -> dict:
    """
    Volume spike: today's volume vs 20-day average.
    spike = ratio >= 2x average.
    """
    if df is None or "Volume" not in df.columns or len(df) < period + 1:
        return {"volume_ratio": None, "volume_signal": None}

    vol = df["Volume"].squeeze()
    avg_vol = vol.rolling(period).mean()

    last_avg = float(avg_vol.iloc[-1])
    if pd.isna(last_avg) or last_avg == 0:
        return {"volume_ratio": None, "volume_signal": None}

    ratio = float(vol.iloc[-1]) / last_avg
    return {
        "volume_ratio": round(ratio, 2),
        "volume_signal": "spike" if ratio >= 2.0 else "normal",
    }


def scan_technicals(df: pd.DataFrame) -> dict:
    """
    Run all technical indicators on an OHLCV DataFrame.
    Returns a flat dict suitable for one row of the screener results table.
    Returns {} on empty/None input.
    """
    if df is None or df.empty:
        return {}

    result: dict = {}

    try:
        # Current price
        close_col = df["Close"].squeeze()
        result["price"] = round(float(close_col.iloc[-1]), 2)

        result.update(calc_moving_averages(df))
        result.update(calc_rsi(df))
        result.update(calc_macd(df))
        result.update(calc_kd(df))
        result.update(calc_bollinger(df))
        result.update(calc_volume_spike(df))

    except Exception as exc:
        logger.warning("scan_technicals failed: %s", exc)

    return result
