"""
Making the chart image and the summary.md report.
Shared by the live bot and the backtest.
"""

from datetime import datetime, timezone

import matplotlib
matplotlib.use("Agg")  # draw to a file; there's no screen on GitHub Actions
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

from bot import config, ledger

# Colors (chosen to be readable for color-blind viewers too)
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_MUTED = "#52514e"
GRID = "#e4e3df"
BOT_COLOR = "#2a78d6"   # blue
SPY_COLOR = "#eb6834"   # orange


def max_drawdown(values: pd.Series) -> float:
    """
    The biggest drop from a previous high, as a negative fraction.
    E.g. -0.25 means at some point the portfolio was 25% below its peak.
    """
    values = pd.Series(values).astype(float)
    if values.empty:
        return 0.0
    running_peak = values.cummax()
    return float((values / running_peak - 1).min())


def plot_vs_spy(dates, bot_values, spy_values, title: str, path,
                bot_label="Momentum bot", spy_label="SPY buy & hold", log_scale=False) -> None:
    """Line chart of the bot vs SPY, saved as a PNG. log_scale=True is better for
    long periods: equal heights then mean equal percentage changes."""
    dates = pd.to_datetime(pd.Series(dates))
    bot_values = pd.Series(bot_values).astype(float).values
    spy_values = pd.Series(spy_values).astype(float).values

    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)

    # SPY drawn first so the bot's line sits on top; zorder keeps legend order bot-first
    ax.plot(dates, bot_values, color=BOT_COLOR, linewidth=2, label=bot_label, zorder=3)
    ax.plot(dates, spy_values, color=SPY_COLOR, linewidth=2, label=spy_label, zorder=2)
    if len(dates) == 1:  # a single point needs a marker to be visible
        ax.scatter(dates, bot_values, color=BOT_COLOR, s=40, zorder=3)
        ax.scatter(dates, spy_values, color=SPY_COLOR, s=40, zorder=3)

    # Direct labels at the right end of each line, with the final value.
    # If the two end points are close together, push the labels apart.
    lo, hi = min(bot_values.min(), spy_values.min()), max(bot_values.max(), spy_values.max())
    close_together = abs(bot_values[-1] - spy_values[-1]) < 0.06 * max(hi - lo, 1e-9)
    bot_on_top = bot_values[-1] >= spy_values[-1]
    nudge = {bot_label: (8 if bot_on_top else -8) if close_together else 0,
             spy_label: (-8 if bot_on_top else 8) if close_together else 0}
    for vals, color, name in ((bot_values, BOT_COLOR, bot_label), (spy_values, SPY_COLOR, spy_label)):
        ax.annotate(f"{name}  ${vals[-1]:,.0f}", xy=(dates.iloc[-1], vals[-1]),
                    xytext=(8, nudge[name]), textcoords="offset points", va="center",
                    fontsize=10, color=TEXT)
        ax.scatter([dates.iloc[-1]], [vals[-1]], color=color, s=30, zorder=4,
                   edgecolors=SURFACE, linewidths=2)

    ax.axhline(config.STARTING_CAPITAL, color=TEXT_MUTED, linewidth=0.8, linestyle=(0, (4, 4)))
    if log_scale:
        ax.set_yscale("log")
        ax.yaxis.set_major_locator(mticker.LogLocator(subs=(1.0, 2.0, 5.0)))
        ax.yaxis.set_minor_formatter(mticker.NullFormatter())
    ax.set_title(title, loc="left", fontsize=14, color=TEXT, pad=30)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"${v:,.0f}"))
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.tick_params(which="both", colors=TEXT_MUTED, labelsize=9, length=0)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    # Legend in one row between the title and the plot
    legend = ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2,
                       frameon=False, fontsize=10, borderaxespad=0.2)
    for t in legend.get_texts():
        t.set_color(TEXT)

    # Date labels: whole days for short histories, months/years for long ones
    span_days = (dates.iloc[-1] - dates.iloc[0]).days
    if span_days < 60:
        ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, span_days // 6)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    else:
        locator = mdates.AutoDateLocator(minticks=4, maxticks=9)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
    fig.subplots_adjust(right=0.80)  # room for the end labels
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def write_live_report(latest_prices: dict) -> None:
    """
    Rebuild performance_chart.png and summary.md from trades.csv and
    performance.csv. `latest_prices` = {ticker: price} for current holdings.
    """
    perf = ledger.load_performance()
    trades = ledger.load_trades()
    holdings, cash = ledger.holdings_and_cash(trades)
    avg_cost = ledger.average_costs(trades)

    lines = ["# Momentum Paper Trading Bot - Summary", "",
             "> PAPER TRADING ONLY - no real money is involved.", "",
             f"_Last updated: {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC_", ""]

    if perf.empty:
        lines += ["No performance data yet. The daily job adds a row after each trading day."]
    else:
        plot_vs_spy(perf["date"], perf["bot_value"], perf["spy_value"],
                    "Momentum bot vs SPY (paper trading, $10,000 start)", config.CHART_PNG)
        last = perf.iloc[-1]
        bot_ret = last["bot_value"] / config.STARTING_CAPITAL - 1
        spy_ret = last["spy_value"] / config.STARTING_CAPITAL - 1
        wr, closed = ledger.win_rate(trades)
        lines += [
            f"Tracking since **{perf.iloc[0]['date']}** (latest: {last['date']})", "",
            "| Metric | Bot | SPY benchmark |",
            "|---|---|---|",
            f"| Value | ${last['bot_value']:,.2f} | ${last['spy_value']:,.2f} |",
            f"| Total return | {bot_ret:+.2%} | {spy_ret:+.2%} |",
            f"| Max drawdown | {max_drawdown(perf['bot_value']):.2%} | {max_drawdown(perf['spy_value']):.2%} |",
            "",
            f"**Return vs SPY:** {bot_ret - spy_ret:+.2%} "
            f"({'ahead of' if bot_ret >= spy_ret else 'behind'} the benchmark)", "",
            f"**Win rate:** {wr:.0%} of {closed} closed trades were sold for a profit"
            if wr is not None else "**Win rate:** n/a (no positions sold yet)", "",
            "![Bot vs SPY](performance_chart.png)", "",
        ]

    lines += ["## Current holdings", ""]
    if not holdings:
        lines += ["None - the bot is 100% in cash.", ""]
    else:
        lines += ["| Ticker | Shares | Avg cost | Last price | Value | Gain/loss |",
                  "|---|---|---|---|---|---|"]
        for tk in sorted(holdings):
            q, cost = holdings[tk], avg_cost.get(tk, float("nan"))
            px = latest_prices.get(tk)
            if px:
                lines.append(f"| {tk} | {q:.4f} | ${cost:,.2f} | ${px:,.2f} | "
                             f"${q * px:,.2f} | {px / cost - 1:+.2%} |")
            else:
                lines.append(f"| {tk} | {q:.4f} | ${cost:,.2f} | n/a | n/a | n/a |")
        lines.append("")
    lines += [f"Cash: ${cash:,.2f}", "",
              "Files: [trades.csv](trades.csv) · [performance.csv](performance.csv) · "
              "[log](logs/bot.log) · [backtest](backtest/backtest_results.md)", ""]
    config.SUMMARY_MD.write_text("\n".join(lines))
