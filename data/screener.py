"""
data/screener.py
Batch stock data fetcher and scanner for the 選股雷達 tab.
All cached functions take tuple arguments (hashable) for st.cache_data compatibility.
"""

import datetime
import logging
from typing import Callable

import pandas as pd
import yfinance as yf
import streamlit as st

import config
from core.technical_indicators import scan_technicals

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Batch price history (technical analysis data)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=config.SCREENER_CACHE_TTL)
def fetch_batch_price_history(
    tickers: tuple[str, ...],
    period: str = "3mo",
) -> dict[str, pd.DataFrame | None]:
    """
    Fetch OHLCV history for multiple tickers in one yf.download() call.
    Returns {ticker: DataFrame or None}.
    Using a single download call is ~10x faster than looping yf.Ticker.
    """
    if not tickers:
        return {}

    try:
        raw = yf.download(
            list(tickers),
            period=period,
            group_by="ticker",
            auto_adjust=True,
            progress=False,
            threads=True,
        )
    except Exception as exc:
        logger.error("yf.download batch failed: %s", exc)
        return {t: None for t in tickers}

    result: dict[str, pd.DataFrame | None] = {}

    if len(tickers) == 1:
        # Single-ticker download returns a flat DataFrame (no ticker level)
        ticker = tickers[0]
        result[ticker] = raw if not raw.empty else None
    else:
        for ticker in tickers:
            try:
                df = raw[ticker].dropna(how="all")
                result[ticker] = df if not df.empty else None
            except (KeyError, TypeError):
                result[ticker] = None

    return result


# ---------------------------------------------------------------------------
# Fundamentals (US stocks via yfinance)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=config.SCREENER_CACHE_TTL)
def fetch_batch_fundamentals(tickers: tuple[str, ...]) -> dict[str, dict]:
    """
    Fetch fundamental metrics for US stocks from yfinance .info.
    Taiwan stocks (.TW) are skipped (yfinance has limited fundamental data for them).
    Returns {ticker: {pe_ratio, pb_ratio, eps_growth, revenue_growth, dividend_yield, sector}}.
    """
    result: dict[str, dict] = {}
    for ticker in tickers:
        if ".TW" in ticker or ".TWO" in ticker:
            result[ticker] = {}
            continue
        try:
            info = yf.Ticker(ticker).info
            pe = info.get("trailingPE")
            pb = info.get("priceToBook")
            eps_g = info.get("earningsGrowth")
            rev_g = info.get("revenueGrowth")
            div_y = info.get("dividendYield")
            result[ticker] = {
                "pe_ratio": round(float(pe), 1) if pe else None,
                "pb_ratio": round(float(pb), 2) if pb else None,
                "eps_growth_pct": round(float(eps_g) * 100, 1) if eps_g else None,
                "revenue_growth_pct": round(float(rev_g) * 100, 1) if rev_g else None,
                "dividend_yield_pct": round(float(div_y) * 100, 2) if div_y else None,
                "sector": info.get("sector", ""),
            }
        except Exception as exc:
            logger.warning("Fundamentals fetch failed for %s: %s", ticker, exc)
            result[ticker] = {}
    return result


# ---------------------------------------------------------------------------
# Taiwan institutional flow (三大法人 + 融資融券) via FinMind
# ---------------------------------------------------------------------------

def fetch_tw_institutional_flow(
    tw_stock_ids: tuple[str, ...],
    api_token: str = "",
) -> dict[str, dict]:
    """
    Fetch Taiwan stock institutional investor flow and margin/short data
    via FinMind API for the past 10 calendar days (≈5 trading days).

    tw_stock_ids: Taiwan stock IDs WITHOUT .TW suffix (e.g. ('2330', '2317')).
    api_token: FinMind token; empty = unauthenticated (300 req/hr free).

    Returns {stock_id: {foreign_buy_5d, trust_buy_5d, dealer_buy_5d,
                         margin_change, short_change}}.
    """
    if not tw_stock_ids:
        return {}

    try:
        from FinMind.data import DataLoader
    except ImportError:
        logger.error("FinMind not installed. Run: pip install finmind")
        return {t: {} for t in tw_stock_ids}

    today = datetime.date.today().isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()

    try:
        dl = DataLoader()
        if api_token:
            dl.login_by_token(api_token=api_token)

        # Fetch institutional investor data for the whole market in one call
        inst_df = dl.taiwan_stock_institutional_investors(
            start_date=start_date,
            end_date=today,
        )

        # Fetch margin / short data
        margin_df = dl.taiwan_stock_margin_purchase_short_sale(
            start_date=start_date,
            end_date=today,
        )

    except Exception as exc:
        logger.error("FinMind API call failed: %s", exc)
        return {t: {} for t in tw_stock_ids}

    result: dict[str, dict] = {}
    id_set = set(tw_stock_ids)

    for stock_id in id_set:
        try:
            inst_s = inst_df[inst_df["stock_id"] == stock_id]

            def _net(name: str) -> int:
                rows = inst_s[inst_s["name"] == name]
                return int(rows["buy"].sum() - rows["sell"].sum()) if not rows.empty else 0

            foreign_net = _net("外資")
            trust_net = _net("投信")
            dealer_net = _net("自營商")

            margin_s = margin_df[margin_df["stock_id"] == stock_id] if not margin_df.empty else pd.DataFrame()
            if not margin_s.empty:
                margin_change = int(
                    margin_s["MarginPurchaseBuy"].sum() - margin_s["MarginPurchaseSell"].sum()
                )
                short_change = int(
                    margin_s["ShortSaleBuy"].sum() - margin_s["ShortSaleSell"].sum()
                )
            else:
                margin_change = 0
                short_change = 0

            result[stock_id] = {
                "foreign_buy_5d": foreign_net,
                "trust_buy_5d": trust_net,
                "dealer_buy_5d": dealer_net,
                "margin_change": margin_change,
                "short_change": short_change,
            }

        except Exception as exc:
            logger.warning("Institutional parse failed for %s: %s", stock_id, exc)
            result[stock_id] = {}

    return result


# ---------------------------------------------------------------------------
# Main scan orchestrator
# ---------------------------------------------------------------------------

def run_full_scan(
    tickers: list[str],
    dimensions: list[str],
    finmind_token: str = "",
    progress_callback: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    """
    Batch scan entry point.

    tickers: list of ticker symbols (e.g. ['NVDA', '2330.TW'])
    dimensions: subset of ['technical', 'fundamental', 'institutional']
    finmind_token: optional FinMind API token for Taiwan institutional data
    progress_callback: callable(current_idx, total) for UI progress bar

    Returns a DataFrame with one row per ticker.
    """
    if not tickers:
        return pd.DataFrame()

    tickers_tuple = tuple(tickers)
    tw_ids = tuple(
        t.replace(".TW", "").replace(".TWO", "")
        for t in tickers if ".TW" in t or ".TWO" in t
    )
    us_tickers = tuple(t for t in tickers if ".TW" not in t and ".TWO" not in t)

    # --- Batch fetch (runs once, results cached) ---
    price_data: dict[str, pd.DataFrame | None] = {}
    if "technical" in dimensions:
        price_data = fetch_batch_price_history(tickers_tuple, config.PRICE_HISTORY_PERIOD)

    fundamental_data: dict[str, dict] = {}
    if "fundamental" in dimensions and us_tickers:
        fundamental_data = fetch_batch_fundamentals(us_tickers)

    institutional_data: dict[str, dict] = {}
    if "institutional" in dimensions and tw_ids:
        institutional_data = fetch_tw_institutional_flow(tw_ids, finmind_token)

    # --- Build result rows ---
    rows: list[dict] = []
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        row: dict = {"ticker": ticker}

        if "technical" in dimensions:
            df = price_data.get(ticker)
            row.update(scan_technicals(df))

        if "fundamental" in dimensions:
            fund = fundamental_data.get(ticker, {})
            row.update(fund)

        if "institutional" in dimensions:
            stock_id = ticker.replace(".TW", "").replace(".TWO", "")
            inst = institutional_data.get(stock_id, {})
            row.update(inst)

        rows.append(row)

        if progress_callback:
            progress_callback(i + 1, total)

    return pd.DataFrame(rows)
