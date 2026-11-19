"""
REBALANCE - run by GitHub Actions every trading day ~10:00am Eastern
(or only on the first trading day of each week if REBALANCE_FREQUENCY is
"weekly" in config.py).

Steps:
  1. Safety checks (paper account only), and make sure today is the right day
     and time to trade.
  2. Download prices, check the crash filter, rank the S&P 500 by momentum.
  3. Sell holdings that fell out of the top 10 (or everything, if the crash
     filter says so).
  4. Buy the new top-10 names with equal-sized positions.
  5. Write trades.csv, the state file, the chart and summary.md.

Run it yourself with:   python -m bot.rebalance
Force a run outside the normal time window (still only while the market is
open, and still only once per day):   python -m bot.rebalance --force

ANY problem (missing data, failed order, ...) is logged and that step is
skipped. The bot never "guesses".
"""

import argparse
import math
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from bot import config, data, ledger, report, strategy
from bot.alpaca_client import AlpacaPaper, PaperOnlyError
from bot.log import get_logger

log = get_logger()
ET = ZoneInfo("America/New_York")


def execute_order(client: AlpacaPaper, ticker: str, side: str, qty: float,
                  reason: str, today: str):
    """
    Place one market order, wait for it to fill, and write it to trades.csv.
    Returns True if (at least part of) the order filled.

    Duplicate protection: every order gets a predictable ID such as
    "mom-20250106-buy-AAPL". If an order with that ID already exists (e.g.
    because this job was re-run), we do NOT place another one; we just look
    up the existing order and make sure it's recorded.
    """
    client_id = f"mom-{today.replace('-', '')}-{side}-{ticker}"
    try:
        order = client.find_order_by_client_id(client_id)
        if order:
            log.info("Order %s already exists (status %s) - not placing it again.",
                     client_id, order.get("status"))
        else:
            log.info("Placing %s order: %s %.4f shares (%s)", side.upper(), ticker, qty, reason)
            order = client.submit_market_order(ticker, qty, side, client_id)
        order = client.wait_for_fill(order)

        filled_qty = float(order.get("filled_qty") or 0)
        fill_price = float(order.get("filled_avg_price") or 0)
        if filled_qty <= 0 or fill_price <= 0:
            log.error("Order %s did not fill (status: %s). Skipping.", client_id, order.get("status"))
            return False
        if ledger.order_already_recorded(order["id"]):
            log.info("Order %s is already in trades.csv.", client_id)
        else:
            ledger.record_trade(today, ticker, side, filled_qty, fill_price, reason, order["id"])
            log.info("FILLED %s %s %.4f @ $%.2f", side.upper(), ticker, filled_qty, fill_price)
        return True
    except Exception as exc:  # network error, order rejected, etc.
        log.error("Order %s failed: %s. Skipping this order.", client_id, exc)
        return False


def is_time_to_rebalance(client: AlpacaPaper, today: str, now_et: datetime, force: bool) -> bool:
    """True on a trading day shortly after the open (and, in weekly mode, only on
    the first trading day of the week)."""
    monday = (now_et.date() - timedelta(days=now_et.weekday())).isoformat()
    calendar = client.get_calendar(monday, today)
    trading_days = [d["date"] for d in calendar]
    if today not in trading_days:
        log.info("%s is not a trading day (weekend or market holiday). Nothing to do.", today)
        return False
    if config.REBALANCE_FREQUENCY == "weekly" and trading_days[0] != today and not force:
        log.info("Already traded this week (first trading day was %s). Nothing to do.", trading_days[0])
        return False

    if not client.get_clock().get("is_open"):
        log.info("Market is not open right now. Nothing to do.")
        return False

    open_time = next(d["open"] for d in calendar if d["date"] == today)  # e.g. "09:30"
    market_open = datetime.fromisoformat(f"{today}T{open_time}").replace(tzinfo=ET)
    minutes_open = (now_et - market_open).total_seconds() / 60
    if minutes_open < config.MIN_MINUTES_AFTER_OPEN:
        log.info("Only %.0f minutes since the open; too early. Nothing to do.", minutes_open)
        return False
    if minutes_open > config.MAX_MINUTES_AFTER_OPEN and not force:
        log.warning("It's %.0f minutes after the open (GitHub was very late); skipping today. "
                    "You can run the workflow manually with force=true.", minutes_open)
        return False
    return True


def run(force: bool = False) -> int:
    log.info("=" * 60)
    log.info("REBALANCE (%s) starting (force=%s)", config.REBALANCE_FREQUENCY, force)

    try:
        client = AlpacaPaper()  # <- all the paper-only safety checks happen here
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

    state = ledger.load_state()
    if state.get("last_rebalance_date") == today:
        log.info("Already rebalanced today (%s). Nothing to do.", today)
        return 0

    try:
        if not is_time_to_rebalance(client, today, now_et, force):
            return 0
    except Exception as exc:
        log.error("Could not check the market calendar/clock: %s. Skipping.", exc)
        return 0

    # ---- 1. Data -----------------------------------------------------------
    try:
        tickers = data.get_sp500_tickers()
        start = (now_et.date() - timedelta(days=420)).isoformat()  # ~14 months
        _, closes = data.get_prices(tickers + [config.BENCHMARK], start, today,
                                    prefer="alpaca", client=client)
    except Exception as exc:
        log.error("Price data failed to load: %s. Skipping this rebalance.", exc)
        return 0

    # Only use COMPLETED days (drop today's half-finished bar, if any).
    closes = closes[closes.index < pd.Timestamp(today)]

    if config.BENCHMARK not in closes:
        log.error("No SPY data, so the crash filter can't be checked. Skipping.")
        return 0
    healthy, spy_price, spy_sma = strategy.market_is_healthy(closes[config.BENCHMARK])
    if healthy is None:
        log.error("Not enough SPY history for the 200-day average. Skipping.")
        return 0
    log.info("Crash filter: SPY $%.2f vs 200-day average $%.2f -> %s", spy_price, spy_sma,
             "OK, invest" if healthy else "BELOW average, hold cash")

    stock_closes = closes.drop(columns=[config.BENCHMARK], errors="ignore")
    scores = strategy.momentum_scores(stock_closes)
    if len(scores) < config.MIN_STOCKS_WITH_DATA:
        log.error("Only %d stocks have enough price history (need %d). Data looks broken; skipping.",
                  len(scores), config.MIN_STOCKS_WITH_DATA)
        return 0
    targets = scores.head(config.TOP_N).index.tolist()
    log.info("Top %d by 12-1 momentum: %s", config.TOP_N,
             ", ".join(f"{t} ({scores[t]:+.0%})" for t in targets))

    # ---- 2. Where do we stand? ----------------------------------------------
    holdings, cash = ledger.holdings_and_cash(ledger.load_trades())
    try:
        positions = client.get_positions()
    except Exception as exc:
        log.error("Could not read positions from Alpaca: %s. Skipping.", exc)
        return 0
    log.info("Bot holdings before: %s | cash $%.2f",
             {k: round(v, 4) for k, v in holdings.items()} or "none", cash)

    sells, buys = strategy.plan_rebalance(holdings, targets, healthy)

    # ---- 3. Sells first (so we have cash for the buys) ---------------------
    for ticker, reason in sells:
        qty = holdings[ticker]
        actual = positions.get(ticker, 0.0)
        if actual + 1e-6 < qty:
            log.warning("Ledger says %s %.4f shares but the account has %.4f; selling only %.4f.",
                        ticker, qty, actual, actual)
            qty = actual
        if qty <= 0:
            log.warning("Nothing to sell for %s. Skipping.", ticker)
            continue
        execute_order(client, ticker, "sell", qty, reason, today)

    # ---- 4. Buys -------------------------------------------------------------
    holdings, cash = ledger.holdings_and_cash(ledger.load_trades())  # refresh after sells
    buys = [t for t in buys if t not in holdings][:max(config.TOP_N - len(holdings), 0)]

    try:
        latest = client.get_latest_prices(list(holdings) + buys)
    except Exception as exc:
        log.warning("Could not get live prices (%s); using yesterday's closes.", exc)
        latest = {}
    for t in list(holdings) + buys:  # fill gaps with yesterday's close
        if t not in latest and t in closes and not math.isnan(closes[t].iloc[-1]):
            latest[t] = float(closes[t].iloc[-1])

    if buys:
        holdings_value = sum(q * latest.get(t, 0.0) for t, q in holdings.items())
        total_value = cash + holdings_value
        target_size = total_value / config.TOP_N           # equal weight
        budget = min(target_size, cash / len(buys)) * (1 - config.CASH_BUFFER)
        log.info("Portfolio value $%.2f -> $%.2f per position; buying %d new stocks with ~$%.2f each",
                 total_value, target_size, len(buys), budget)

        for ticker in buys:
            price = latest.get(ticker)
            if not price:
                log.error("No price for %s. Skipping this buy.", ticker)
                continue
            try:
                asset = client.get_asset(ticker)
            except Exception as exc:
                log.error("Could not look up %s: %s. Skipping this buy.", ticker, exc)
                continue
            if not asset or not asset.get("tradable"):
                log.error("%s is not tradable on Alpaca. Skipping this buy.", ticker)
                continue
            raw_qty = budget / price
            if asset.get("fractionable"):
                qty = math.floor(raw_qty * 10_000) / 10_000  # round DOWN to 4 decimals
            else:
                qty = math.floor(raw_qty)                     # whole shares only
            if qty <= 0:
                log.warning("Budget $%.2f is too small for one share of %s ($%.2f). Skipping.",
                            budget, ticker, price)
                continue
            execute_order(client, ticker, "buy", qty, f"entered top {config.TOP_N}", today)
    elif healthy:
        log.info("No new stocks to buy; the top %d hasn't changed.", config.TOP_N)

    # ---- 5. Save state and reports -------------------------------------------
    holdings, cash = ledger.holdings_and_cash(ledger.load_trades())
    state.update({
        "last_rebalance_date": today,
        "crash_filter_ok": bool(healthy),
        "spy_price": round(spy_price, 2),
        "spy_200d_average": round(spy_sma, 2),
        "top_10": targets,
        "holdings": holdings,
        "cash": round(cash, 2),
    })
    ledger.save_state(state)
    try:
        report.write_live_report(latest)
    except Exception as exc:
        log.error("Could not write the report: %s", exc)
    log.info("Rebalance finished. Holdings: %s | cash $%.2f", list(holdings) or "none", cash)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Momentum rebalance (paper trading only)")
    parser.add_argument("--force", action="store_true",
                        help="run outside the normal time window (market must be open)")
    args = parser.parse_args()
    sys.exit(run(force=args.force))
