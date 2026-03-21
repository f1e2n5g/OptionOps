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
