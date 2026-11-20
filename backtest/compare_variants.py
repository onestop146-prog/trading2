"""
COMPARE SETTINGS: what happens if the bot holds more stocks, or uses a
shorter momentum window? Mainly to see how the NUMBER OF TRADES changes, and
what that does to returns and risk.

Every setting uses the same data, the same start date, daily rebalancing,
the crash filter, and the same 0.1% cost per trade. The same survivorship
bias warning as the main backtest applies to all of them.

Run it with:   python -m backtest.compare_variants
Writes backtest/variants.md
"""

import sys

import pandas as pd

from backtest import run_backtest as bt
from bot import config, data, ledger
from bot.log import get_logger

log = get_logger()

# (label, how many stocks to hold, lookback days, skip days)
VARIANTS = [
    ("Current: top 10, 12-1 momentum", 10, 252, 21),
    ("Top 20, 12-1 momentum", 20, 252, 21),
    ("Top 30, 12-1 momentum", 30, 252, 21),
    ("Top 10, 6-1 momentum", 10, 126, 21),
    ("Top 10, 3-1 momentum", 10, 63, 21),
    ("Top 20, 6-1 momentum", 20, 126, 21),
]


def main() -> int:
    tickers = data.get_sp500_tickers()
    end = (pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    opens, closes = data.get_prices(tickers + [config.BENCHMARK], bt.DATA_START, end, prefer="yahoo")
    now_et = pd.Timestamp.now(tz="America/New_York")
    if now_et.hour < 17:  # drop today's unfinished bar during market hours
        closes = closes[closes.index < now_et.normalize().tz_localize(None)]
        opens = opens.reindex(closes.index)

    saved = (config.TOP_N, config.LOOKBACK_DAYS, config.SKIP_DAYS)
    rows, spy_row, surv_row = [], None, None
    for label, top_n, lookback, skip in VARIANTS:
        config.TOP_N, config.LOOKBACK_DAYS, config.SKIP_DAYS = top_n, lookback, skip
        equity, trades = bt.run_backtest(opens, closes, frequency="daily")
        dates = pd.to_datetime(equity["date"])
        years = (dates.iloc[-1] - dates.iloc[0]).days / 365.25
        st = bt.stats(equity["bot_value"], dates)
        wr, closed = ledger.win_rate(trades)
        rows.append((label, len(trades) / years, closed / years, st, wr))
        log.info("%s: %d trades/yr, CAGR %+.1f%%, max DD %.0f%%",
                 label, len(trades) / years, st["cagr"] * 100, st["max_dd"] * 100)
        if spy_row is None:
            spy_row = bt.stats(equity["spy_value"], dates)
            surv_row = bt.stats(equity["survivors_value"], dates)
            period = f"{dates.iloc[0].date()} to {dates.iloc[-1].date()}"
    config.TOP_N, config.LOOKBACK_DAYS, config.SKIP_DAYS = saved

    lines = [
        "# Comparing settings: more trades vs. returns and risk", "",
        f"_Period {period} · daily rebalancing · crash filter on · 0.1% cost per trade · "
        "today's S&P 500 list (survivorship bias applies to every row)_", "",
        "**Closed trades** = a stock bought and later sold. That's what the win rate is measured on, "
        "so it's the \"sample size\" that matters.", "",
        "| Setting | Trades / year | Closed trades / year | $10,000 became | Yearly return | "
        "Max drawdown | Sharpe | Win rate |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for label, tpy, cpy, st, wr in rows:
        lines.append(f"| {label} | {tpy:,.0f} | {cpy:,.0f} | ${st['final']:,.0f} | {st['cagr']:+.1%} | "
                     f"{st['max_dd']:.1%} | {st['sharpe']:.2f} | "
                     f"{f'{wr:.0%}' if wr is not None else 'n/a'} |")
    for label, st in (("SPY buy & hold", spy_row), ("Today's S&P 500, equal weight (bias yardstick)", surv_row)):
        lines.append(f"| {label} | 0 | 0 | ${st['final']:,.0f} | {st['cagr']:+.1%} | "
                     f"{st['max_dd']:.1%} | {st['sharpe']:.2f} | n/a |")
    lines += [
        "", "- **More stocks** (top 20/30): more trades and more diversification, usually smoother "
        "but closer to the market's return.",
        "- **Shorter window** (6-1, 3-1): reacts faster, so it trades a lot more. That's a different, "
        "noisier strategy, and the extra trading costs add up.", "",
    ]
    out = config.BACKTEST_DIR / "variants.md"
    out.write_text("\n".join(lines))
    log.info("Wrote %s", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
