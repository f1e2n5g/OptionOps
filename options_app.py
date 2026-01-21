import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# --- 頁面設定 (Page Configuration) ---
st.set_page_config(layout="wide", page_title="Von's OptionOps")

# --- 軍師風格樣式 (Custom CSS) ---
st.markdown("""
<style>
    .metric-card {
        background-color: #1e1e1e;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #333;
    }
    h1, h2, h3 { color: #00ff41 !important; font-family: 'Courier New', monospace; }
</style>
""", unsafe_allow_html=True)

# --- 標題區 ---
st.title("🦅 OptionOps: 戰略期權分析儀")
st.markdown("**User:** Von (武貪修羅) | **Status:** Active | **Target:** Hedging & Speculation")

# --- 側邊欄：戰術輸入 (Sidebar Inputs) ---
st.sidebar.header("🎯 標的設定")
ticker_symbol = st.sidebar.text_input("輸入美股代號", value="NVDA").upper()

# --- 修正後的數據獲取邏輯 ---
# 1. 建立 Ticker 物件
stock = yf.Ticker(ticker_symbol)

# 2. 獲取價格 (只回傳數值，可快取)
@st.cache_data(ttl=60)
def get_price_history(symbol):
    temp_ticker = yf.Ticker(symbol)
    hist = temp_ticker.history(period="1d")
    if hist.empty:
        return None
    return hist.iloc[-1].Close

# 3. 獲取期權鏈 (修正重點：拆解成 DataFrame 回傳)
@st.cache_data(ttl=60)
def get_option_chain_dfs(symbol, date):
    temp_ticker = yf.Ticker(symbol)
    opt = temp_ticker.option_chain(date)
    # 直接回傳兩個 DataFrame，這樣 Streamlit 就能快樂地 pickle 它們了
    return opt.calls, opt.puts

try:
    current_price = get_price_history(ticker_symbol)
    
    if current_price is None:
        st.error(f"❌ 找不到代號 {ticker_symbol} 的數據，請確認輸入正確。")
        st.stop()

    # 顯示即時股價
    st.sidebar.metric(label=f"{ticker_symbol} 現價", value=f"${current_price:.2f}")

    # 選擇到期日
    expirations = stock.options
    if not expirations:
        st.error("❌ 無法獲取期權數據，可能該標的無期權交易。")
        st.stop()
        
    selected_date = st.sidebar.selectbox("📅 選擇到期日 (Expiration)", expirations)

    # 獲取期權數據 (接收兩個 DataFrame)
    calls, puts = get_option_chain_dfs(ticker_symbol, selected_date)
    
    # 這裡過濾一下，只看價平 (ATM) 附近的履約價
    strike_range = st.sidebar.slider("履約價範圍 (Strike Price Range)", 
                                     float(current_price*0.7), 
                                     float(current_price*1.3), 
                                     (float(current_price*0.85), float(current_price*1.15)))
    
    # 過濾數據
    calls_filtered = calls[(calls['strike'] >= strike_range[0]) & (calls['strike'] <= strike_range[1])]
    puts_filtered = puts[(puts['strike'] >= strike_range[0]) & (puts['strike'] <= strike_range[1])]

    # --- 主戰場：數據儀表板 ---
    
    # 1. 市場情緒 (Sentiment Analysis)
    st.subheader("📊 1. 戰場情緒 (Put/Call Ratio)")
    total_call_oi = calls['openInterest'].sum()
    total_put_oi = puts['openInterest'].sum()
    pc_ratio = total_put_oi / total_call_oi if total_call_oi > 0 else 0
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Call Open Interest (多軍)", f"{total_call_oi:,}")
    col2.metric("Put Open Interest (空軍)", f"{total_put_oi:,}")
    col3.metric("P/C Ratio", f"{pc_ratio:.2f}", delta_color="inverse")
    
    if pc_ratio > 1.5:
        st.warning("⚠️ 市場極度恐慌 (Bearish) - Puts 過多，可能會有軋空 (Short Squeeze) 或暴跌。")
    elif pc_ratio < 0.7:
        st.success("🚀 市場極度樂觀 (Bullish) - Calls 過多，留意回檔風險。")
    else:
        st.info("⚖️ 市場情緒中性 (Neutral)")

    # 2. 籌碼分佈 (Open Interest Distribution)
    st.subheader(f"🛡️ 2. 主力防線分析 ({selected_date})")
    st.markdown("觀察 Open Interest (未平倉量) 最高的履約價，通常是**支撐**或**壓力**。")
    
    fig = go.Figure()
    fig.add_trace(go.Bar(x=calls_filtered['strike'], y=calls_filtered['openInterest'], name='Calls (壓力)', marker_color='green'))
    fig.add_trace(go.Bar(x=puts_filtered['strike'], y=puts_filtered['openInterest'], name='Puts (支撐)', marker_color='red'))
    
    # 標示現價
    fig.add_vline(x=current_price, line_width=2, line_dash="dash", line_color="yellow", annotation_text="Current Price")
    
    fig.update_layout(barmode='overlay', title='Open Interest Distribution', xaxis_title='Strike Price', yaxis_title='Open Interest')
    fig.update_traces(opacity=0.6)
    st.plotly_chart(fig, use_container_width=True)

    # 3. 避險計算器 (Hedging Calculator)
    st.subheader("🛡️ 3. 資產防禦計算 (Protective Put)")
    st.markdown("假設你想為手上的持股買保險，防止股價大跌。")
    
    with st.expander("打開計算器 (Calculator)", expanded=True):
        shares_owned = st.number_input("持有股數 (Shares)", value=100, step=10)
        
        # 防呆機制：確保有 puts 可選
        otm_puts = puts_filtered[puts_filtered['strike'] < current_price]
        
        if not otm_puts.empty:
            insurance_strike = st.selectbox("選擇保險履約價 (Strike)", otm_puts['strike'].sort_values(ascending=False))
            
            target_put = puts[puts['strike'] == insurance_strike].iloc[0]
            put_price = target_put['lastPrice']
            contracts_needed = shares_owned / 100
            total_cost = put_price * 100 * contracts_needed
            
            c1, c2 = st.columns(2)
            c1.metric("所需合約數 (Contracts)", f"{contracts_needed:.1f} 張")
            c2.metric("預估保險成本 (Cost)", f"${total_cost:.2f} USD")
            
            st.markdown(f"""
            **戰略解讀：**
            如果你支付 **${total_cost:.2f}** 購買此 Put，在 {selected_date} 到期前，
            即便 {ticker_symbol} 跌到 0 元，你都有權利以 **${insurance_strike}** 賣出股票。
            這就是為你的資產穿上防彈衣。
            """)
        else:
            st.warning("⚠️ 目前範圍內沒有價外 Put (OTM Puts) 可供選擇，請調整履約價範圍。")

    # 4. 原始數據 (Raw Data)
    with st.expander("🔍 查看詳細報價表 (Option Chain Data)"):
        st.write("Calls (看漲):")
        st.dataframe(calls_filtered[['strike', 'lastPrice', 'bid', 'ask', 'volume', 'openInterest', 'impliedVolatility']])
        st.write("Puts (看跌):")
        st.dataframe(puts_filtered[['strike', 'lastPrice', 'bid', 'ask', 'volume', 'openInterest', 'impliedVolatility']])

except Exception as e:
    st.error(f"系統發生錯誤：{e}")
    st.markdown("---")
    st.markdown("*Tip: 確保你在美股交易時段或盤後有網絡連接。*")