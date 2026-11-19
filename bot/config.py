"""
All the settings for the bot live in this one file.

If you want to experiment (e.g. hold 20 stocks instead of 10), change the
numbers here. Everything else reads from this file.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# SAFETY: PAPER TRADING ONLY
# ---------------------------------------------------------------------------
# This is Alpaca's *paper* (fake money) trading server. It is hardcoded on
# purpose. The bot never reads the trading URL from anywhere else, and
# alpaca_client.py refuses to run if anything looks like the live server.
PAPER_TRADING_URL = "https://paper-api.alpaca.markets"

# Alpaca's market-data server (prices only; it cannot place orders).
MARKET_DATA_URL = "https://data.alpaca.markets"

# ---------------------------------------------------------------------------
# MONEY
# ---------------------------------------------------------------------------
# The bot pretends it only has this much money, even if the paper account has
# more (new Alpaca paper accounts usually start with $100,000).
STARTING_CAPITAL = 10_000.0

# Keep a small cushion when buying, because the price can move a little
# between the moment we calculate the order and the moment it fills.
CASH_BUFFER = 0.01  # 1%

# ---------------------------------------------------------------------------
# STRATEGY
# ---------------------------------------------------------------------------
TOP_N = 10               # how many stocks to hold
# How often to rebalance: "daily" (every trading day ~10am ET) or "weekly"
# (first trading day of each week). The backtest compares both.
REBALANCE_FREQUENCY = "daily"
LOOKBACK_DAYS = 252      # ~12 months of trading days
SKIP_DAYS = 21           # ~1 month of trading days (the "-1" in "12-1")
SMA_DAYS = 200           # crash filter: SPY's 200-day moving average
BENCHMARK = "SPY"

# If fewer than this many S&P 500 stocks have usable price data, something is
# wrong with the data source, so we skip trading rather than guess.
MIN_STOCKS_WITH_DATA = 400

# The rebalance only happens if we are at least this many minutes after the
# market opens (so the opening chaos has settled) ...
MIN_MINUTES_AFTER_OPEN = 25
# ... and no later than this many minutes after the open (GitHub Actions can be
# delayed; if it's very late we'd rather skip than trade at a random time).
MAX_MINUTES_AFTER_OPEN = 300

# ---------------------------------------------------------------------------
# FILES (all paths are relative to the repository root)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
TRADES_CSV = ROOT / "trades.csv"
PERFORMANCE_CSV = ROOT / "performance.csv"
SUMMARY_MD = ROOT / "summary.md"
CHART_PNG = ROOT / "performance_chart.png"
LOG_FILE = ROOT / "logs" / "bot.log"
STATE_FILE = ROOT / "state" / "bot_state.json"
SP500_CACHE = ROOT / "data" / "sp500_tickers.csv"

BACKTEST_DIR = ROOT / "backtest"
