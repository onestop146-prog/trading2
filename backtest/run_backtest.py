"""
BACKTEST: how would the momentum strategy have done over the last ~15 years?

It replays history one trading day at a time using the SAME strategy code
as the live bot (bot/strategy.py):
  * On each rebalance day (every trading day, or the first trading day of each
    week - see REBALANCE_FREQUENCY in bot/config.py), rank stocks using prices up to the
    PREVIOUS close (no peeking at the future), then trade at that day's
    OPENING price (the live bot trades ~30 minutes after the open).
  * Every day, value the portfolio at the closing price.
  * Compare against $10,000 put into SPY on day one and held.

!!! SURVIVORSHIP BIAS WARNING !!!
We use TODAY's S&P 500 list for the whole history. Those are the companies
that survived and grew enough to be in the index today. Companies that
crashed, went bankrupt or got kicked out of the index are missing, and the
strategy can never "accidentally" buy them in the backtest. This makes the
backtest look BETTER than reality - possibly a lot better for a momentum
strategy, which loves stocks that went up (some of which later collapsed).
Treat the results as an optimistic upper bound, not a forecast.

Run it with:   python -m backtest.run_backtest
Outputs go to the backtest/ folder.
"""

import sys
from datetime import date

import numpy as np
import pandas as pd

from bot import config, data, ledger, report, strategy
from bot.log import get_logger

log = get_logger()

DATA_START = "2009-01-01"   # ~1 year of warm-up data before trading starts
SLIPPAGE = 0.001            # assume we lose 0.1% on every trade (spread, etc.)
OUT = config.BACKTEST_DIR


def run_backtest(opens: pd.DataFrame, closes: pd.DataFrame,
                 frequency: str = config.REBALANCE_FREQUENCY):
    """
    Simulate the strategy. Returns (equity DataFrame, trades DataFrame).
    `frequency` is "daily" or "weekly".
    `opens`/`closes`: one row per trading day, one column per ticker incl. SPY.
    """
    closes = closes.ffill(limit=5)        # fill tiny gaps in the data
    opens = opens.reindex_like(closes)
    spy = closes[config.BENCHMARK]
    stocks = [c for c in closes.columns if c != config.BENCHMARK]

    if frequency == "daily":
        rebalance_days = set(closes.index)                   # every trading day
    else:
        # First trading day of each calendar week
        iso = closes.index.isocalendar()
        week_id = iso["year"].astype(str) + "-" + iso["week"].astype(str)
        rebalance_days = set(closes.index[~week_id.duplicated()])

    # Survivorship-bias yardstick: an equal-weight mix of ALL of today's S&P 500
    # stocks (rebalanced daily). It has no strategy at all, so any big lead it
    # has over SPY comes mostly from knowing in advance which companies survived.
    survivor_daily_returns = closes[stocks].pct_change(fill_method=None).mean(axis=1)

    # Start after one year of history (the same start date for every setting,
    # so comparisons between settings are fair)
    first = max(252, config.LOOKBACK_DAYS, config.SMA_DAYS) + 1
    cash = config.STARTING_CAPITAL
    holdings = {}          # ticker -> shares
    trades = []
    equity = []
    spy_shares = None
    survivors_value = config.STARTING_CAPITAL

    def price_at_open(ticker, i):
        """Opening price; falls back to the previous close if missing."""
        px = opens[ticker].iloc[i]
        return float(px) if pd.notna(px) and px > 0 else float(closes[ticker].iloc[i - 1])

    for i in range(first, len(closes)):
        day = closes.index[i]
        if spy_shares is None:
            spy_shares = config.STARTING_CAPITAL / price_at_open(config.BENCHMARK, i)

        if day in rebalance_days:
            history = closes.iloc[:i]                       # data up to yesterday only
            healthy, _, _ = strategy.market_is_healthy(history[config.BENCHMARK])
            targets = strategy.top_stocks(history[stocks])
            if healthy is not None and len(targets) == config.TOP_N:
                sells, buys = strategy.plan_rebalance(holdings, targets, healthy)

                for ticker, reason in sells:
                    px = price_at_open(ticker, i) * (1 - SLIPPAGE)
                    q = holdings.pop(ticker)
                    cash += q * px
                    trades.append((day.date(), ticker, "sell", q, px, reason))

                if buys:
                    value = cash + sum(q * price_at_open(t, i) for t, q in holdings.items())
                    budget = min(value / config.TOP_N, cash / len(buys)) * (1 - config.CASH_BUFFER)
                    for ticker in buys:
                        px = price_at_open(ticker, i) * (1 + SLIPPAGE)
                        q = budget / px
                        cash -= q * px
                        holdings[ticker] = q
                        trades.append((day.date(), ticker, "buy", q, px,
                                       f"entered top {config.TOP_N}"))

        # Value everything at today's close
        value = cash + sum(q * float(closes[t].iloc[i]) for t, q in holdings.items())
        if i > first:
            survivors_value *= 1 + survivor_daily_returns.iloc[i]
        equity.append((day, value, spy_shares * float(spy.iloc[i]), survivors_value, len(holdings)))

    equity = pd.DataFrame(equity, columns=["date", "bot_value", "spy_value", "survivors_value",
                                           "num_holdings"])
    trades = pd.DataFrame(trades, columns=["date", "ticker", "side", "shares", "price", "reason"])
    return equity, trades


def stats(values: pd.Series, dates: pd.Series) -> dict:
    """Summary numbers for one equity curve."""
    values = values.astype(float).reset_index(drop=True)
    years = (dates.iloc[-1] - dates.iloc[0]).days / 365.25
    daily = values.pct_change().dropna()
    return {
        "final": values.iloc[-1],
        "total": values.iloc[-1] / config.STARTING_CAPITAL - 1,
        "cagr": (values.iloc[-1] / values.iloc[0]) ** (1 / years) - 1,
        "max_dd": report.max_drawdown(values),
        "vol": daily.std() * np.sqrt(252),
        "sharpe": daily.mean() / daily.std() * np.sqrt(252) if daily.std() > 0 else 0.0,
    }


def write_results(equity: pd.DataFrame, trades: pd.DataFrame, source_note: str,
                  comparison: dict = None) -> None:
    """Save the CSVs, chart and backtest_results.md. `comparison` optionally maps
    "daily"/"weekly" -> (equity, trades) to show both frequencies side by side."""
    OUT.mkdir(exist_ok=True)
    equity.round({"bot_value": 2, "spy_value": 2, "survivors_value": 2}).to_csv(OUT / "backtest_equity.csv", index=False)
    trades.round({"shares": 4, "price": 2}).to_csv(OUT / "backtest_trades.csv", index=False)

    dates = pd.to_datetime(equity["date"])
    start, end = dates.iloc[0].date(), dates.iloc[-1].date()
    report.plot_vs_spy(dates, equity["bot_value"], equity["spy_value"],
                       f"Backtest: 12-1 momentum (top {config.TOP_N}, {config.REBALANCE_FREQUENCY}) vs SPY, "
                       f"{start.year}-{end.year}",
                       OUT / "backtest_chart.png", spy_label="SPY buy & hold", log_scale=True)

    b = stats(equity["bot_value"], dates)
    s = stats(equity["spy_value"], dates)
    sv = stats(equity["survivors_value"], dates)
    wr, closed = ledger.win_rate(trades)
    in_cash = (equity["num_holdings"] == 0).mean()

    # Calendar-year returns
    yearly = equity.assign(year=dates.dt.year).groupby("year")[["bot_value", "spy_value"]].last()
    prev = yearly.shift(1)
    prev.iloc[0] = config.STARTING_CAPITAL
    yr = yearly / prev - 1

    lines = [
        "# Backtest results: 12-1 momentum vs SPY", "",
        "> ## ⚠️ Survivorship bias warning",
        "> This backtest uses **today's** S&P 500 list for the whole history. Companies that",
        "> collapsed, went bankrupt or were removed from the index are missing, so the strategy",
        "> could never pick a future loser by accident. Momentum strategies are especially",
        "> flattered by this, because they buy stocks that have already risen a lot - and some of",
        "> the real-life winners later crashed and left the index. **Real results would very likely",
        "> have been worse than shown here.** Treat this as an optimistic upper bound, not a forecast.",
        "",
        f"_Generated {date.today()} · Period: {start} to {end} · Data: {source_note}_", "",
        "![Backtest chart](backtest_chart.png)", "",
        "_The chart uses a log scale, so equal vertical distances mean equal % changes._", "",
        "| | Momentum bot | SPY buy & hold | Today's S&P 500, equal weight* |",
        "|---|---|---|---|",
        f"| $10,000 became | ${b['final']:,.0f} | ${s['final']:,.0f} | ${sv['final']:,.0f} |",
        f"| Total return | {b['total']:+.0%} | {s['total']:+.0%} | {sv['total']:+.0%} |",
        f"| Yearly return (CAGR) | {b['cagr']:+.1%} | {s['cagr']:+.1%} | {sv['cagr']:+.1%} |",
        f"| Max drawdown | {b['max_dd']:.1%} | {s['max_dd']:.1%} | {sv['max_dd']:.1%} |",
        f"| Volatility (per year) | {b['vol']:.1%} | {s['vol']:.1%} | {sv['vol']:.1%} |",
        f"| Sharpe ratio (no risk-free rate) | {b['sharpe']:.2f} | {s['sharpe']:.2f} | {sv['sharpe']:.2f} |",
        "",
        "\\* **Survivorship-bias yardstick:** simply owning *all* of today's S&P 500 members in equal",
        "amounts, with no strategy. Its lead over SPY "
        f"({sv['cagr'] - s['cagr']:+.1%} per year) is roughly how much the survivor list alone flatters",
        "results. The bot's lead over **this** column "
        f"({b['cagr'] - sv['cagr']:+.1%} per year) is a fairer (still optimistic) guess at what momentum adds.",
        "",
        f"- **Return vs SPY:** {b['total'] - s['total']:+.0%} total, "
        f"{b['cagr'] - s['cagr']:+.1%} per year",
        f"- **Win rate:** {wr:.0%} of {closed} closed trades sold above their purchase price"
        if wr is not None else "- **Win rate:** n/a",
        f"- **Right now** the bot is {1 - equity['bot_value'].iloc[-1] / equity['bot_value'].max():.0%} "
        "below its all-time high in this backtest (0% = at a new high)",
        f"- **Time spent in cash** (crash filter): {in_cash:.0%} of trading days",
        f"- **Trades:** {len(trades)} total; assumed {SLIPPAGE:.1%} slippage per trade, no commissions",
        "",
    ]
    if comparison:
        lines += [
            "## Daily vs weekly rebalancing", "",
            f"The bot is set to **{config.REBALANCE_FREQUENCY}** (change `REBALANCE_FREQUENCY` in "
            "`bot/config.py`). Same rules, same data, only how often it checks:", "",
            "| Rebalance | $10,000 became | Yearly return | Max drawdown | Trades |",
            "|---|---|---|---|---|",
        ]
        for freq, (eq, tr) in comparison.items():
            st = stats(eq["bot_value"], pd.to_datetime(eq["date"]))
            lines.append(f"| {freq} | ${st['final']:,.0f} | {st['cagr']:+.1%} | "
                         f"{st['max_dd']:.1%} | {len(tr):,} |")
        lines += ["", "_Daily checks react faster to the crash filter and to new leaders, but trade "
                  f"more, and each trade costs an assumed {SLIPPAGE:.1%}._", ""]
    lines += [
        "## Year by year", "",
        "| Year | Bot | SPY | Difference |",
        "|---|---|---|---|",
    ]
    for year, row in yr.iterrows():
        lines.append(f"| {year} | {row['bot_value']:+.1%} | {row['spy_value']:+.1%} | "
                     f"{row['bot_value'] - row['spy_value']:+.1%} |")
    lines += [
        "", "## How the backtest works", "",
        "- Universe: today's S&P 500 members (see warning above).",
        f"- Rebalance {config.REBALANCE_FREQUENCY}: rank stocks by the return from ~12 months ago to "
        "~1 month ago, using prices up to the previous close.",
        f"- Hold the top {config.TOP_N}, equal weight. Only stocks that drop out of the top "
        f"{config.TOP_N} are sold; new entries are bought at the opening price.",
        "- Crash filter: if SPY closed below its 200-day average, sell everything and wait in cash.",
        "- Prices are adjusted for splits and dividends (dividends are effectively reinvested).",
        "- Other things a backtest can't capture: taxes, real fill prices, data errors, and the "
        "fact that the strategy rules were picked knowing momentum worked in the past.",
        "",
        "Files: [daily equity](backtest_equity.csv) · [all trades](backtest_trades.csv)", "",
    ]
    (OUT / "backtest_results.md").write_text("\n".join(lines))
    log.info("Backtest: bot %+.0f%% (CAGR %+.1f%%, max DD %.0f%%) vs SPY %+.0f%% (CAGR %+.1f%%)",
             b["total"] * 100, b["cagr"] * 100, b["max_dd"] * 100, s["total"] * 100, s["cagr"] * 100)


def main() -> int:
    log.info("=" * 60)
    log.info("BACKTEST starting")
    tickers = data.get_sp500_tickers()
    end = (pd.Timestamp.today() + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    opens, closes = data.get_prices(tickers + [config.BENCHMARK], DATA_START, end, prefer="yahoo")
    # If the market is still open, today's "close" is just the latest price; drop it.
    now_et = pd.Timestamp.now(tz="America/New_York")
    if now_et.hour < 17:
        closes = closes[closes.index < now_et.normalize().tz_localize(None)]
        opens = opens.reindex(closes.index)
    if config.BENCHMARK not in closes:
        log.error("No SPY data; cannot run the backtest.")
        return 1
    years = (closes.index[-1] - closes.index[0]).days / 365.25
    source_note = (f"{closes.shape[1] - 1} of {len(tickers)} current S&P 500 stocks had data "
                   f"({years:.1f} years of prices, first year used as warm-up)")
    equity, trades = run_backtest(opens, closes)

    # Also run the other rebalance frequency, just to compare
    other = "weekly" if config.REBALANCE_FREQUENCY == "daily" else "daily"
    other_equity, other_trades = run_backtest(opens, closes, frequency=other)
    comparison = {config.REBALANCE_FREQUENCY: (equity, trades), other: (other_equity, other_trades)}

    write_results(equity, trades, source_note, comparison)
    return 0


if __name__ == "__main__":
    sys.exit(main())
