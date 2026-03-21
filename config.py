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
