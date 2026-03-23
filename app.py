"""
app.py — OptionOps Commercial Dashboard
Main Streamlit entry point.
Run with:  streamlit run app.py
"""

import logging
import streamlit as st

from config import (
    APP_TITLE, APP_ICON,
    STRIKE_RANGE_MIN, STRIKE_RANGE_MAX,
    STRIKE_RANGE_DEFAULT_LOW, STRIKE_RANGE_DEFAULT_HIGH,
)
from data.fetcher import get_price, get_expirations, get_option_chain
from core.calculations import calc_pc_ratio, calc_max_pain
from ui.components import (
    render_sentiment_section,
    render_positioning_section,
    render_hedging_calculator,
    render_bs_section,
    render_data_section,
    render_screener_tab,
)

logging.basicConfig(level=logging.INFO)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title=f"{APP_ICON} {APP_TITLE}",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    h1, h2, h3 { color: #00ff41 !important; font-family: 'Courier New', monospace; }
    .stMetric label { color: #aaaaaa !important; }
    div[data-testid="stSidebar"] { background-color: #111111; }
    .block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Sidebar — inputs
# ---------------------------------------------------------------------------
st.sidebar.title(f"{APP_ICON} OptionOps")
st.sidebar.markdown("**Strategic Options Analytics**")
st.sidebar.markdown("---")

ticker_symbol = st.sidebar.text_input("美股代號 (Ticker)", value="NVDA").upper().strip()

if not ticker_symbol:
    st.warning("請輸入股票代號。")
    st.stop()

# Fetch price
with st.spinner(f"獲取 {ticker_symbol} 即時股價..."):
    current_price = get_price(ticker_symbol)

if current_price is None:
    st.error(f"❌ 找不到 **{ticker_symbol}** 的數據。請確認代號正確且有網路連線。")
    st.stop()

st.sidebar.metric(label=f"{ticker_symbol} 現價", value=f"${current_price:.2f}")

# Fetch expirations
with st.spinner("載入到期日清單..."):
    expirations = get_expirations(ticker_symbol)

if not expirations:
    st.error(f"❌ **{ticker_symbol}** 沒有可交易的期權，請換其他標的。")
    st.stop()

selected_date = st.sidebar.selectbox("到期日 (Expiration)", expirations)

# Strike range filter
strike_range = st.sidebar.slider(
    "顯示行權價範圍",
    min_value=float(current_price * STRIKE_RANGE_MIN),
    max_value=float(current_price * STRIKE_RANGE_MAX),
    value=(
        float(current_price * STRIKE_RANGE_DEFAULT_LOW),
        float(current_price * STRIKE_RANGE_DEFAULT_HIGH),
    ),
    step=0.5,
)

# Fetch option chain
with st.spinner(f"載入 {ticker_symbol} 期權鏈數據..."):
    calls_raw, puts_raw = get_option_chain(ticker_symbol, selected_date)

if calls_raw.empty and puts_raw.empty:
    st.error("❌ 無法獲取期權鏈數據，請稍後再試或選擇不同到期日。")
    st.stop()

# Filtered DataFrames (for charts / hedging)
calls_filtered = calls_raw[
    (calls_raw["strike"] >= strike_range[0]) & (calls_raw["strike"] <= strike_range[1])
]
puts_filtered = puts_raw[
    (puts_raw["strike"] >= strike_range[0]) & (puts_raw["strike"] <= strike_range[1])
]

# Core calculations (use full chain for accuracy)
pc_ratio = calc_pc_ratio(calls_raw, puts_raw)
max_pain = calc_max_pain(calls_raw, puts_raw)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title(f"{APP_ICON} OptionOps: 戰略期權分析儀")
st.markdown(
    f"**標的:** `{ticker_symbol}` &nbsp;|&nbsp; "
    f"**現價:** `${current_price:.2f}` &nbsp;|&nbsp; "
    f"**到期日:** `{selected_date}` &nbsp;|&nbsp; "
    f"**P/C Ratio:** `{pc_ratio:.2f}` &nbsp;|&nbsp; "
    f"**Max Pain:** `${max_pain:.2f}`"
)
st.markdown("---")

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 戰場情緒",
    "🛡️ 主力佈局",
    "🧮 避險計算",
    "🔬 Black-Scholes",
    "📋 原始數據",
    "🔍 選股雷達",
])

with tab1:
    st.subheader("📊 戰場情緒分析 (Put/Call Ratio)")
    render_sentiment_section(calls_raw, puts_raw, pc_ratio)

with tab2:
    st.subheader("🛡️ 主力防線分析 (Open Interest + Max Pain)")
    render_positioning_section(calls_filtered, puts_filtered, current_price, max_pain, selected_date)

with tab3:
    st.subheader("🧮 資產防禦計算 (Protective Put Hedging)")
    render_hedging_calculator(puts_raw, current_price, selected_date, ticker_symbol)

with tab4:
    st.subheader("🔬 Black-Scholes 定價分析")
    render_bs_section(calls_filtered, puts_filtered, current_price, selected_date)

with tab5:
    st.subheader("📋 詳細期權報價表")
    render_data_section(calls_filtered, puts_filtered)

with tab6:
    st.subheader("🔍 選股雷達 — 多維度批量選股")
    render_screener_tab()
