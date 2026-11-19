"""
DAILY PERFORMANCE LOG - run by GitHub Actions every weekday after the close.

It does NOT trade. It just:
  1. Works out what the bot's holdings are worth at today's closing prices.
  2. Works out what the pretend "$10,000 in SPY on day one" is worth.
  3. Adds a row to performance.csv and refreshes the chart and summary.md.

Run it yourself with:   python -m bot.daily
"""

import argparse
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from bot import config, data, ledger, report
from bot.alpaca_client import AlpacaPaper, PaperOnlyError
from bot.log import get_logger

log = get_logger()
ET = ZoneInfo("America/New_York")


def run(force: bool = False) -> int:
    log.info("=" * 60)
    log.info("DAILY PERFORMANCE LOG starting")

    try:
        client = AlpacaPaper()  # paper-only safety checks
    except PaperOnlyError as exc:
        log.critical("SAFETY STOP: %s", exc)
        return 1
    except Exception as exc:
        # Usually a missing/wrong API key. Nothing was traded, but we exit with an
        # error so the run shows a red X in GitHub Actions and you notice.
        log.error("Could not connect to Alpaca: %s. Check your GitHub Secrets.", exc)
        return 1

    now_et = datetime.now(ET)
    today = now_et.date().isoformat()

    try:
        if not client.get_calendar(today, today):
            log.info("%s is not a trading day (weekend or holiday). Nothing to log.", today)
            return 0
        if client.get_clock().get("is_open") and not force:
            log.info("Market is still open; closing prices aren't final yet. Nothing to log.")
            return 0
    except Exception as exc:
        log.error("Could not check the market calendar/clock: %s. Skipping.", exc)
        return 0

    holdings, cash = ledger.holdings_and_cash(ledger.load_trades())
    symbols = sorted(set(holdings) | {config.BENCHMARK})

    try:
        start = (now_et.date() - timedelta(days=14)).isoformat()
        end = (now_et.date() + timedelta(days=1)).isoformat()
        _, closes = data.get_prices(symbols, start, end, prefer="alpaca", client=client)
    except Exception as exc:
        log.error("Price data failed to load: %s. Not logging today.", exc)
        return 0

    closes = closes[closes.index <= pd.Timestamp(today)]
    if config.BENCHMARK not in closes or closes[config.BENCHMARK].dropna().empty:
        log.error("No SPY price. Not logging today.")
        return 0
    spy = closes[config.BENCHMARK].dropna()
    if spy.index[-1] != pd.Timestamp(today):
        log.error("Today's closing prices aren't available yet (latest is %s). Not logging today.",
                  spy.index[-1].date())
        return 0

    # Latest known closing price for each holding
    prices = {}
    for t in holdings:
        series = closes[t].dropna() if t in closes else pd.Series(dtype=float)
        if series.empty:
            log.error("No price for holding %s. Not logging today (value would be wrong).", t)
            return 0
        if series.index[-1] != pd.Timestamp(today):
            log.warning("%s has no price for today; using %s close.", t, series.index[-1].date())
        prices[t] = float(series.iloc[-1])

    bot_value = cash + sum(q * prices[t] for t, q in holdings.items())
    perf = ledger.record_performance(today, bot_value, cash, float(spy.iloc[-1]), len(holdings))
    last = perf.iloc[-1]
    log.info("Logged %s: bot $%.2f | SPY benchmark $%.2f | cash $%.2f | %d holdings",
             today, last["bot_value"], last["spy_value"], cash, len(holdings))

    try:
        report.write_live_report(prices)
    except Exception as exc:
        log.error("Could not write the report: %s", exc)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Daily performance logger (no trading)")
    parser.add_argument("--force", action="store_true", help="log even if the market is open")
    sys.exit(run(force=parser.parse_args().force))
