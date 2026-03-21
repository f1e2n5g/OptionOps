"""
ui/components.py
Reusable Streamlit UI sections.
Each render_* function owns one logical block of the dashboard.
"""

import io
import streamlit as st
import pandas as pd

from config import PC_RATIO_BEARISH, PC_RATIO_BULLISH, RISK_FREE_RATE
from core.calculations import (
    calc_hedging_cost,
    add_theoretical_prices,
)
from ui.charts import (
    oi_distribution_chart,
    volatility_smile_chart,
    bs_comparison_chart,
)


# ---------------------------------------------------------------------------
# Tab 1 — Sentiment
# ---------------------------------------------------------------------------

def render_sentiment_section(
    calls_df: pd.DataFrame,
    puts_df: pd.DataFrame,
    pc_ratio: float,
) -> None:
    """Put/Call ratio metrics and sentiment signal."""
    total_call_oi = int(calls_df["openInterest"].sum())
    total_put_oi = int(puts_df["openInterest"].sum())

    col1, col2, col3 = st.columns(3)
    col1.metric("Call OI (多軍)", f"{total_call_oi:,}")
    col2.metric("Put OI (空軍)", f"{total_put_oi:,}")
    col3.metric("P/C Ratio", f"{pc_ratio:.2f}")

    if pc_ratio > PC_RATIO_BEARISH:
        st.warning(
            f"⚠️ **極度恐慌 (Bearish)** — P/C Ratio {pc_ratio:.2f} > {PC_RATIO_BEARISH}  \n"
            "Put 過多，可能出現軋空 (Short Squeeze) 或進一步下跌。"
        )
    elif pc_ratio < PC_RATIO_BULLISH:
        st.success(
            f"🚀 **極度樂觀 (Bullish)** — P/C Ratio {pc_ratio:.2f} < {PC_RATIO_BULLISH}  \n"
            "Call 過多，留意回檔修正風險。"
        )
    else:
        st.info(f"⚖️ **情緒中性 (Neutral)** — P/C Ratio {pc_ratio:.2f}，市場無明顯偏向。")


# ---------------------------------------------------------------------------
# Tab 2 — Positioning
# ---------------------------------------------------------------------------

def render_positioning_section(
    calls_df: pd.DataFrame,
    puts_df: pd.DataFrame,
    current_price: float,
    max_pain: float,
    selected_date: str,
) -> None:
    """OI distribution chart + Volatility Smile."""
    col1, col2 = st.columns(2)
    col1.metric("Max Pain 行權點", f"${max_pain:.2f}")
    diff = current_price - max_pain
    col2.metric(
        "現價與 Max Pain 差距",
        f"${abs(diff):.2f}",
        delta=f"{'現價偏高' if diff > 0 else '現價偏低'} {abs(diff):.2f}",
        delta_color="inverse",
    )
    st.caption("Max Pain = 讓最多期權到期作廢的行權價，市場上行至該點機率高。")

    st.plotly_chart(
        oi_distribution_chart(calls_df, puts_df, current_price, max_pain, selected_date),
        use_container_width=True,
    )

    st.subheader("📈 波動率微笑 (Volatility Smile / Skew)")
    st.caption("IV 越高 = 市場對該行權價的波動預期越大。尾部 IV 走高 = Skew 向下傾斜，反映下行恐慌。")
    st.plotly_chart(
        volatility_smile_chart(calls_df, puts_df, current_price, selected_date),
        use_container_width=True,
    )


# ---------------------------------------------------------------------------
# Tab 3 — Hedging Calculator
# ---------------------------------------------------------------------------

def render_hedging_calculator(
    puts_df: pd.DataFrame,
    current_price: float,
    selected_date: str,
    ticker: str,
) -> None:
    """Protective Put hedging calculator with portfolio CSV upload."""

    # --- Single-stock calculator ---
    st.subheader("🛡️ 單股避險計算")
    with st.expander("打開計算器", expanded=True):
        shares_owned = st.number_input(
            "持有股數 (Shares)", min_value=1, max_value=100_000, value=100, step=10
        )

        # Show ALL OTM puts (not limited to the filtered range)
        otm_puts = puts_df[puts_df["strike"] < current_price].copy()

        if otm_puts.empty:
            st.warning("⚠️ 目前無 OTM Put 可選，請確認到期日是否有效。")
            return

        insurance_strike = st.selectbox(
            "選擇保險行權價 (Strike)",
            otm_puts["strike"].sort_values(ascending=False).tolist(),
        )
        target_put = puts_df[puts_df["strike"] == insurance_strike].iloc[0]
        put_price = float(target_put["lastPrice"])

        contracts, total_cost = calc_hedging_cost(shares_owned, put_price)

        c1, c2 = st.columns(2)
        c1.metric("所需合約數", f"{contracts:.1f} 張")
        c2.metric("預估保險成本", f"${total_cost:,.2f} USD")

        breakeven = insurance_strike - put_price
        protection_pct = (current_price - insurance_strike) / current_price * 100
        st.markdown(f"""
        **戰略解讀：**
        - 支付 **${total_cost:,.2f}** 購買此 Put 保險
        - 到期日 {selected_date} 前，{ticker} 跌至任何價格，你都有權以 **${insurance_strike}** 賣出
        - 保護範圍：現價下跌 **{protection_pct:.1f}%** 以內
        - 損益兩平點：**${breakeven:.2f}**（低於此價才開始獲利）
        """)

    # --- Portfolio CSV upload ---
    st.subheader("📂 投資組合批量避險")
    st.caption("上傳 CSV 檔案（欄位：`ticker`, `shares`），系統自動計算各股保險成本。")

    template_csv = "ticker,shares\nNVDA,100\nTSLA,50\nAAPL,200\n"
    st.download_button(
        label="下載 CSV 範本",
        data=template_csv,
        file_name="portfolio_template.csv",
        mime="text/csv",
    )

    uploaded = st.file_uploader("上傳投資組合 CSV", type=["csv"])
    if uploaded is not None:
        _render_portfolio_hedging(uploaded, selected_date)


def _render_portfolio_hedging(uploaded_file, selected_date: str) -> None:
    """Parse uploaded CSV and show hedging summary per ticker."""
    from data.fetcher import get_price, get_option_chain

    try:
        portfolio = pd.read_csv(uploaded_file)
        if "ticker" not in portfolio.columns or "shares" not in portfolio.columns:
            st.error("CSV 格式錯誤：需包含 `ticker` 和 `shares` 欄位。")
            return

        portfolio["ticker"] = portfolio["ticker"].str.upper().str.strip()
        portfolio["shares"] = pd.to_numeric(portfolio["shares"], errors="coerce").fillna(0).astype(int)
        portfolio = portfolio[portfolio["shares"] > 0].head(10)  # cap at 10 tickers

        results = []
        for _, row in portfolio.iterrows():
            sym = row["ticker"]
            shares = int(row["shares"])
            price = get_price(sym)
            if price is None:
                results.append({"Ticker": sym, "Shares": shares, "現價": "N/A", "保險成本": "無法獲取"})
                continue

            _, puts = get_option_chain(sym, selected_date)
            otm_puts = puts[puts["strike"] < price]
            if otm_puts.empty:
                results.append({"Ticker": sym, "Shares": shares, "現價": f"${price:.2f}", "保險成本": "無 OTM Put"})
                continue

            # Use the highest OTM strike (closest to ATM)
            best_put = otm_puts.loc[otm_puts["strike"].idxmax()]
            _, cost = calc_hedging_cost(shares, float(best_put["lastPrice"]))
            results.append({
                "Ticker": sym,
                "Shares": shares,
                "現價": f"${price:.2f}",
                "保險行權價": f"${best_put['strike']:.2f}",
                "保險成本": f"${cost:,.2f}",
            })

        df_results = pd.DataFrame(results)
        st.dataframe(df_results, use_container_width=True)

        total = sum(
            float(r["保險成本"].replace("$", "").replace(",", ""))
            for r in results
            if r["保險成本"] not in ("N/A", "無法獲取", "無 OTM Put")
        )
        st.metric("投資組合總保險成本", f"${total:,.2f} USD")

    except Exception as exc:
        st.error(f"處理 CSV 時發生錯誤：{exc}")


# ---------------------------------------------------------------------------
# Tab 4 — Black-Scholes Analysis
# ---------------------------------------------------------------------------

def render_bs_section(
    calls_df: pd.DataFrame,
    puts_df: pd.DataFrame,
    current_price: float,
    expiry_date: str,
) -> None:
    """Black-Scholes theoretical price comparison and Greeks table."""
    st.caption(
        "Black-Scholes 理論價格以各合約的 Implied Volatility 計算。"
        "市場價格 > BS 理論價 → 可能高估；< 理論價 → 可能低估。"
    )

    opt_type = st.radio("選擇期權類型", ["Calls", "Puts"], horizontal=True)
    df_raw = calls_df if opt_type == "Calls" else puts_df
    ot = "call" if opt_type == "Calls" else "put"

    with st.spinner("計算 Black-Scholes 理論價格與 Greeks..."):
        df_bs = add_theoretical_prices(df_raw, current_price, expiry_date, RISK_FREE_RATE, ot)

    # Price comparison chart
    st.plotly_chart(
        bs_comparison_chart(df_bs, ot, current_price),
        use_container_width=True,
    )

    # Mispricing column
    df_bs["溢價/折價"] = (df_bs["lastPrice"] - df_bs["BS_Price"]).round(4)

    display_cols = ["strike", "lastPrice", "BS_Price", "溢價/折價",
                    "impliedVolatility", "delta", "gamma", "theta", "vega"]
    display_cols = [c for c in display_cols if c in df_bs.columns]

    st.dataframe(
        df_bs[display_cols].rename(columns={
            "strike": "行權價",
            "lastPrice": "市場價",
            "BS_Price": "BS 理論價",
            "impliedVolatility": "IV",
        }),
        use_container_width=True,
    )


# ---------------------------------------------------------------------------
# Tab — Raw Data + CSV Export
# ---------------------------------------------------------------------------

def render_data_section(calls_df: pd.DataFrame, puts_df: pd.DataFrame) -> None:
    """Filtered option chain tables with CSV download buttons."""
    cols = ["strike", "lastPrice", "bid", "ask", "volume", "openInterest", "impliedVolatility"]

    col1, col2 = st.columns(2)
    with col1:
        st.write("**Calls (看漲)**")
        calls_display = calls_df[[c for c in cols if c in calls_df.columns]]
        st.dataframe(calls_display, use_container_width=True)
        st.download_button(
            "⬇️ 下載 Calls CSV",
            data=calls_display.to_csv(index=False).encode("utf-8"),
            file_name="calls.csv",
            mime="text/csv",
        )

    with col2:
        st.write("**Puts (看跌)**")
        puts_display = puts_df[[c for c in cols if c in puts_df.columns]]
        st.dataframe(puts_display, use_container_width=True)
        st.download_button(
            "⬇️ 下載 Puts CSV",
            data=puts_display.to_csv(index=False).encode("utf-8"),
            file_name="puts.csv",
            mime="text/csv",
        )


# ---------------------------------------------------------------------------
# Tab 6 — 選股雷達 (Stock Screener)
# ---------------------------------------------------------------------------

# Signal → human-readable label mapping
_SIGNAL_LABELS = {
    "golden_cross":  "黃金交叉 ✅",
    "death_cross":   "死亡交叉 ❌",
    "bullish_cross": "MACD 多頭 ✅",
    "bearish_cross": "MACD 空頭 ❌",
    "oversold":      "超賣 ✅",
    "overbought":    "超買 ⚠️",
    "near_lower":    "近下軌 ✅",
    "near_upper":    "近上軌 ⚠️",
    "inside":        "帶內",
    "spike":         "量能爆增 ⚡",
    "normal":        "正常",
    "neutral":       "中性",
}


def _style_screener(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    """Apply green/red background to signal columns."""
    signal_cols = [c for c in df.columns if c.endswith("_signal")]

    def _cell_color(val: str) -> str:
        if not isinstance(val, str):
            return ""
        if any(k in val for k in ("✅", "黃金", "多頭", "超賣", "近下軌")):
            return "background-color: #1a3a1a; color: #00ff41"
        if any(k in val for k in ("❌", "死亡", "空頭", "超買", "⚠️")):
            return "background-color: #3a1a1a; color: #ff6b6b"
        if "⚡" in val:
            return "background-color: #2a2a1a; color: #ffff00"
        return ""

    styler = df.style
    for col in signal_cols:
        if col in df.columns:
            styler = styler.applymap(_cell_color, subset=[col])
    return styler


def render_screener_tab() -> None:
    """
    選股雷達 — full UI for the stock screener tab.
    Handles stock pool selection, filter setup, scan execution, and results display.
    """
    from config import (
        TW_DEFAULT_POOL, US_DEFAULT_POOL, SP500_TOP30_POOL,
        SCREENER_MAX_TICKERS, FINMIND_TOKEN,
    )
    from data.screener import run_full_scan

    st.markdown(
        "多維度批量股票掃描：**技術面**（MA/RSI/MACD/KD）× **財務面**（P/E/EPS）× "
        "**籌碼面**（三大法人/融資券，台股）"
    )

    # -----------------------------------------------------------------------
    # Section 1: Stock Pool
    # -----------------------------------------------------------------------
    st.subheader("📂 Step 1：設定股票池")
    pool_mode = st.radio("選擇模式", ["預設股票池", "自訂輸入"], horizontal=True)

    if pool_mode == "預設股票池":
        preset = st.selectbox(
            "選擇預設池",
            ["台灣 50 成分股", "美股科技龍頭 (20支)", "S&P 500 前30大"],
        )
        pool_map = {
            "台灣 50 成分股": TW_DEFAULT_POOL,
            "美股科技龍頭 (20支)": US_DEFAULT_POOL,
            "S&P 500 前30大": SP500_TOP30_POOL,
        }
        selected_pool = pool_map[preset]
        with st.expander(f"股票池預覽 ({len(selected_pool)} 支)"):
            st.write(", ".join(selected_pool))
    else:
        raw_input = st.text_area(
            "輸入股票代碼（每行一個，台股請加 .TW，例如 2330.TW）",
            placeholder="NVDA\nAAPL\n2330.TW\n2317.TW",
            height=150,
        )
        selected_pool = [
            t.strip().upper()
            for t in raw_input.replace(",", "\n").splitlines()
            if t.strip()
        ]
        if len(selected_pool) > SCREENER_MAX_TICKERS:
            st.warning(f"⚠️ 超過上限 {SCREENER_MAX_TICKERS} 支，已截斷。")
            selected_pool = selected_pool[:SCREENER_MAX_TICKERS]
        if selected_pool:
            st.caption(f"已輸入 {len(selected_pool)} 支：{', '.join(selected_pool[:10])}"
                       + (" ..." if len(selected_pool) > 10 else ""))

    if not selected_pool:
        st.info("請選擇或輸入至少一支股票。")
        return

    # -----------------------------------------------------------------------
    # Section 2: Filter Conditions
    # -----------------------------------------------------------------------
    st.subheader("⚙️ Step 2：設定篩選條件")

    dimensions = st.multiselect(
        "分析維度（可多選）",
        ["技術面", "財務面（美股）", "籌碼面（台股）"],
        default=["技術面"],
    )

    dim_keys = []
    if "技術面" in dimensions:
        dim_keys.append("technical")
    if "財務面（美股）" in dimensions:
        dim_keys.append("fundamental")
    if "籌碼面（台股）" in dimensions:
        dim_keys.append("institutional")

    # Collect filter params
    filters: dict = {}

    col_t, col_f, col_i = st.columns(3)

    if "技術面" in dimensions:
        with col_t:
            st.markdown("**📊 技術面**")
            filters["ma_signal"] = st.selectbox(
                "MA 均線訊號", ["全部", "黃金交叉", "死亡交叉"], key="f_ma"
            )
            filters["rsi_min"], filters["rsi_max"] = st.slider(
                "RSI 範圍", 0, 100, (0, 100), key="f_rsi"
            )
            filters["macd_signal"] = st.selectbox(
                "MACD 訊號", ["全部", "多頭交叉", "空頭交叉"], key="f_macd"
            )
            filters["kd_signal"] = st.selectbox(
                "KD 訊號", ["全部", "黃金交叉", "死亡交叉", "超賣", "超買"], key="f_kd"
            )
            filters["volume_spike"] = st.checkbox("只顯示量能爆增 (≥2x均量)", key="f_vol")

    if "財務面（美股）" in dimensions:
        with col_f:
            st.markdown("**💰 財務面（美股）**")
            filters["pe_max"] = st.number_input("P/E 比 ≤", value=50.0, min_value=0.0, key="f_pe")
            filters["eps_growth_min"] = st.number_input(
                "EPS 年增率 ≥ (%)", value=0.0, key="f_eps"
            )
            filters["div_yield_min"] = st.number_input(
                "殖利率 ≥ (%)", value=0.0, min_value=0.0, key="f_div"
            )

    if "籌碼面（台股）" in dimensions:
        with col_i:
            st.markdown("**🏦 籌碼面（台股）**")
            filters["foreign_flow"] = st.selectbox(
                "外資近5日", ["全部", "買超 > 0", "賣超 < 0"], key="f_foreign"
            )
            filters["trust_flow"] = st.selectbox(
                "投信近5日", ["全部", "買超 > 0", "賣超 < 0"], key="f_trust"
            )
            filters["margin_flow"] = st.selectbox(
                "融資近5日", ["全部", "增加", "減少"], key="f_margin"
            )
            finmind_token = st.text_input(
                "FinMind Token（選填）",
                value=FINMIND_TOKEN,
                type="password",
                help="免費註冊 finmindtrade.com 可獲得 600 req/hr",
                key="f_fm_token",
            )
    else:
        finmind_token = FINMIND_TOKEN

    # -----------------------------------------------------------------------
    # Section 3: Run Scan
    # -----------------------------------------------------------------------
    st.subheader("🚀 Step 3：執行掃描")

    if not dim_keys:
        st.warning("請至少選擇一個分析維度。")
        return

    if st.button("🔍 開始掃描", type="primary", use_container_width=True):
        progress_bar = st.progress(0, text="掃描中...")
        status_box = st.empty()

        def _progress(current: int, total: int) -> None:
            pct = int(current / total * 100)
            progress_bar.progress(pct, text=f"掃描中 {current}/{total}...")

        with st.spinner("正在批量抓取數據並計算指標..."):
            results_df = run_full_scan(
                tickers=selected_pool,
                dimensions=dim_keys,
                finmind_token=finmind_token if "institutional" in dim_keys else "",
                progress_callback=_progress,
            )

        progress_bar.empty()
        status_box.empty()

        if results_df.empty:
            st.warning("沒有取得任何數據，請確認網路連線與股票代碼。")
            st.session_state["screener_results"] = pd.DataFrame()
            return

        # ---- Apply filters ----
        filtered = results_df.copy()

        if "technical" in dim_keys:
            ma_filter = filters.get("ma_signal", "全部")
            if ma_filter == "黃金交叉":
                filtered = filtered[filtered.get("ma_signal", pd.Series()) == "golden_cross"] \
                    if "ma_signal" in filtered.columns else filtered
            elif ma_filter == "死亡交叉":
                filtered = filtered[filtered.get("ma_signal", pd.Series()) == "death_cross"] \
                    if "ma_signal" in filtered.columns else filtered

            if "rsi" in filtered.columns:
                rsi_min, rsi_max = filters.get("rsi_min", 0), filters.get("rsi_max", 100)
                mask = filtered["rsi"].isna() | (
                    (filtered["rsi"] >= rsi_min) & (filtered["rsi"] <= rsi_max)
                )
                filtered = filtered[mask]

            macd_filter = filters.get("macd_signal", "全部")
            if macd_filter == "多頭交叉" and "macd_signal" in filtered.columns:
                filtered = filtered[filtered["macd_signal"] == "bullish_cross"]
            elif macd_filter == "空頭交叉" and "macd_signal" in filtered.columns:
                filtered = filtered[filtered["macd_signal"] == "bearish_cross"]

            kd_filter = filters.get("kd_signal", "全部")
            kd_map = {"黃金交叉": "golden_cross", "死亡交叉": "death_cross",
                      "超賣": "oversold", "超買": "overbought"}
            if kd_filter != "全部" and "kd_signal" in filtered.columns:
                filtered = filtered[filtered["kd_signal"] == kd_map.get(kd_filter, kd_filter)]

            if filters.get("volume_spike") and "volume_signal" in filtered.columns:
                filtered = filtered[filtered["volume_signal"] == "spike"]

        if "fundamental" in dim_keys:
            pe_max = filters.get("pe_max", 9999)
            if "pe_ratio" in filtered.columns and pe_max < 9999:
                filtered = filtered[filtered["pe_ratio"].isna() | (filtered["pe_ratio"] <= pe_max)]

            eps_min = filters.get("eps_growth_min", 0.0)
            if "eps_growth_pct" in filtered.columns and eps_min > 0:
                filtered = filtered[filtered["eps_growth_pct"].isna() | (filtered["eps_growth_pct"] >= eps_min)]

            div_min = filters.get("div_yield_min", 0.0)
            if "dividend_yield_pct" in filtered.columns and div_min > 0:
                filtered = filtered[filtered["dividend_yield_pct"].isna() | (filtered["dividend_yield_pct"] >= div_min)]

        if "institutional" in dim_keys:
            foreign_filter = filters.get("foreign_flow", "全部")
            if foreign_filter == "買超 > 0" and "foreign_buy_5d" in filtered.columns:
                filtered = filtered[filtered["foreign_buy_5d"] > 0]
            elif foreign_filter == "賣超 < 0" and "foreign_buy_5d" in filtered.columns:
                filtered = filtered[filtered["foreign_buy_5d"] < 0]

            trust_filter = filters.get("trust_flow", "全部")
            if trust_filter == "買超 > 0" and "trust_buy_5d" in filtered.columns:
                filtered = filtered[filtered["trust_buy_5d"] > 0]
            elif trust_filter == "賣超 < 0" and "trust_buy_5d" in filtered.columns:
                filtered = filtered[filtered["trust_buy_5d"] < 0]

            margin_filter = filters.get("margin_flow", "全部")
            if margin_filter == "增加" and "margin_change" in filtered.columns:
                filtered = filtered[filtered["margin_change"] > 0]
            elif margin_filter == "減少" and "margin_change" in filtered.columns:
                filtered = filtered[filtered["margin_change"] < 0]

        st.session_state["screener_results"] = filtered
        st.session_state["screener_raw"] = results_df

    # -----------------------------------------------------------------------
    # Section 4: Display Results
    # -----------------------------------------------------------------------
    filtered = st.session_state.get("screener_results")
    raw = st.session_state.get("screener_raw")

    if filtered is None:
        return

    total_scanned = len(raw) if raw is not None else 0
    st.success(f"掃描完成：共 {total_scanned} 支，篩選後 **{len(filtered)}** 支符合條件。")

    if filtered.empty:
        st.info("沒有股票符合目前的篩選條件，請放寬條件後重新掃描。")
        return

    # Build display DataFrame — translate signal values to human-readable
    display_df = filtered.copy()
    signal_cols = [c for c in display_df.columns if c.endswith("_signal")]
    for col in signal_cols:
        display_df[col] = display_df[col].map(lambda v: _SIGNAL_LABELS.get(v, v) if isinstance(v, str) else v)

    # Column order: ticker first, then price, then signals, then numerics
    priority_cols = ["ticker", "price"]
    signal_display = [c for c in signal_cols if c in display_df.columns]
    numeric_cols = [
        c for c in display_df.columns
        if c not in priority_cols + signal_display
        and display_df[c].dtype in (float, int, "float64", "int64")
    ]
    ordered_cols = priority_cols + signal_display + numeric_cols
    ordered_cols = [c for c in ordered_cols if c in display_df.columns]
    display_df = display_df[ordered_cols]

    # Rename columns to Chinese
    col_rename = {
        "ticker": "代號",
        "price": "現價",
        "ma_signal": "MA 訊號",
        "rsi": "RSI",
        "rsi_signal": "RSI 訊號",
        "macd_signal": "MACD 訊號",
        "k": "K 值",
        "d": "D 值",
        "kd_signal": "KD 訊號",
        "bb_signal": "布林訊號",
        "volume_ratio": "量比",
        "volume_signal": "量能訊號",
        "pe_ratio": "P/E",
        "pb_ratio": "P/B",
        "eps_growth_pct": "EPS增長%",
        "revenue_growth_pct": "營收增長%",
        "dividend_yield_pct": "殖利率%",
        "sector": "產業",
        "foreign_buy_5d": "外資近5日",
        "trust_buy_5d": "投信近5日",
        "dealer_buy_5d": "自營商近5日",
        "margin_change": "融資增減",
        "short_change": "融券增減",
    }
    display_df = display_df.rename(columns={k: v for k, v in col_rename.items() if k in display_df.columns})

    # Apply color styling
    styled = _style_screener(display_df)
    st.dataframe(styled, use_container_width=True, height=500)

    # Ticker quick-select to bring into main analysis
    st.markdown("---")
    col_a, col_b = st.columns([3, 1])
    with col_a:
        hit_tickers = filtered["ticker"].tolist() if "ticker" in filtered.columns else []
        if hit_tickers:
            chosen = st.selectbox("快速帶入分析（切換主 Sidebar）", hit_tickers, key="screener_pick")
            if st.button("➡️ 切換到此標的分析", key="screener_switch"):
                st.session_state["main_ticker"] = chosen
                st.info(f"已設定 {chosen}，請在左側 Sidebar 輸入欄更新代號後重新載入。")
    with col_b:
        if not filtered.empty:
            csv_data = filtered.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📥 下載篩選結果 CSV",
                data=csv_data,
                file_name="screener_results.csv",
                mime="text/csv",
                use_container_width=True,
            )
