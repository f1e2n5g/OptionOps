# OptionOps Configuration
# Centralized constants — edit here to change app-wide behavior

# P/C Ratio sentiment thresholds
PC_RATIO_BEARISH = 1.5   # Above this → extreme fear / bearish
PC_RATIO_BULLISH = 0.7   # Below this → extreme greed / bullish

# Default strike price range (fraction of current price)
STRIKE_RANGE_MIN = 0.70
STRIKE_RANGE_MAX = 1.30
STRIKE_RANGE_DEFAULT_LOW = 0.85
STRIKE_RANGE_DEFAULT_HIGH = 1.15

# Data cache TTL (seconds)
CACHE_TTL = 60

# Black-Scholes risk-free rate (annualized)
RISK_FREE_RATE = 0.05

# App metadata
APP_TITLE = "OptionOps: 戰略期權分析儀"
APP_ICON = "🦅"

# ---------------------------------------------------------------------------
# 選股雷達 (Stock Screener) settings
# ---------------------------------------------------------------------------

SCREENER_CACHE_TTL = 300       # 5 minutes for batch scan cache
SCREENER_MAX_TICKERS = 200     # hard cap per scan

# RSI thresholds
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# KD thresholds
KD_OVERSOLD = 20
KD_OVERBOUGHT = 80

# Price history period for computing indicators
PRICE_HISTORY_PERIOD = "3mo"

# FinMind API token (optional — empty string = unauthenticated, 300 req/hr)
FINMIND_TOKEN = ""

# Preset: Taiwan 50 component stocks (TWSE: 0050)
TW_DEFAULT_POOL = [
    "2330.TW", "2317.TW", "2454.TW", "2382.TW", "2308.TW",
    "2881.TW", "2882.TW", "2303.TW", "2412.TW", "1301.TW",
    "2886.TW", "2891.TW", "2884.TW", "2885.TW", "2892.TW",
    "2207.TW", "2002.TW", "1303.TW", "1326.TW", "2395.TW",
    "3711.TW", "2379.TW", "2301.TW", "2357.TW", "2408.TW",
    "3034.TW", "2327.TW", "2344.TW", "4938.TW", "2353.TW",
    "5880.TW", "2887.TW", "3045.TW", "2883.TW", "9910.TW",
    "2880.TW", "1402.TW", "2609.TW", "2615.TW", "2603.TW",
    "2618.TW", "6505.TW", "1216.TW", "2912.TW", "2105.TW",
    "1101.TW", "3008.TW", "2474.TW", "2376.TW", "6669.TW",
]

# Preset: US tech leaders
US_DEFAULT_POOL = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "META",
    "AMZN", "TSLA", "AMD", "AVGO", "QCOM",
    "INTC", "MU", "TSM", "ASML", "ORCL",
    "CRM", "ADBE", "TXN", "AMAT", "LRCX",
]

# Preset: S&P 500 top 30 by market cap
SP500_TOP30_POOL = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "META", "BRK-B", "LLY", "TSLA", "AVGO",
    "JPM", "UNH", "XOM", "V", "PG",
    "MA", "COST", "HD", "JNJ", "ABBV",
    "MRK", "WMT", "NFLX", "BAC", "CRM",
    "CVX", "AMD", "KO", "PEP", "MCD",
]
