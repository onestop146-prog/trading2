"""
The bot's bookkeeping.

trades.csv is the bot's "ledger": every filled trade is written there, and
the bot works out its cash and holdings by replaying that file:

    cash     = $10,000 - money spent on buys + money received from sells
    holdings = shares bought - shares sold, per ticker

This is how the bot sticks to its own $10,000 even if the paper account
has $100,000 in it.

performance.csv gets one row per trading day with the value of the bot and
of the pretend "$10,000 in SPY on day one" benchmark.
"""

import json
from datetime import datetime, timezone

import pandas as pd

from bot import config

TRADE_COLUMNS = ["date", "ticker", "side", "shares", "price", "value", "reason", "order_id"]
PERF_COLUMNS = ["date", "bot_value", "spy_value", "bot_cash", "spy_price", "num_holdings"]


# ----- trades -----------------------------------------------------------------

def load_trades() -> pd.DataFrame:
    if not config.TRADES_CSV.exists():
        return pd.DataFrame(columns=TRADE_COLUMNS)
    return pd.read_csv(config.TRADES_CSV)


def record_trade(date: str, ticker: str, side: str, shares: float, price: float,
                 reason: str, order_id: str = "") -> None:
    """Append one filled trade to trades.csv (creating it if needed)."""
    row = pd.DataFrame([{
        "date": date, "ticker": ticker, "side": side,
        "shares": round(shares, 6), "price": round(price, 4),
        "value": round(shares * price, 2), "reason": reason, "order_id": order_id,
    }], columns=TRADE_COLUMNS)
    write_header = not config.TRADES_CSV.exists()
    row.to_csv(config.TRADES_CSV, mode="a", header=write_header, index=False)


def holdings_and_cash(trades: pd.DataFrame):
    """Replay the ledger. Returns ({ticker: shares}, cash)."""
    cash = config.STARTING_CAPITAL
    holdings = {}
    for _, t in trades.iterrows():
        shares, value = float(t["shares"]), float(t["shares"]) * float(t["price"])
        if t["side"] == "buy":
            cash -= value
            holdings[t["ticker"]] = holdings.get(t["ticker"], 0.0) + shares
        else:
            cash += value
            holdings[t["ticker"]] = holdings.get(t["ticker"], 0.0) - shares
    # Drop anything that's (essentially) zero shares
    holdings = {k: round(v, 6) for k, v in holdings.items() if abs(v) > 1e-6}
    return holdings, cash


def order_already_recorded(order_id: str) -> bool:
    trades = load_trades()
    return bool(order_id) and order_id in set(trades["order_id"].astype(str))


def _replay_cost_basis(trades: pd.DataFrame):
    """
    Walk through the trades in order, tracking the average price paid for
    each stock. Returns (average_cost_of_current_holdings, wins, closed_trades)
    where a "win" is a sell at a higher price than the average price paid.
    """
    cost, shares = {}, {}
    wins = closed = 0
    for _, t in trades.iterrows():
        tk, q, p = t["ticker"], float(t["shares"]), float(t["price"])
        if t["side"] == "buy":
            cost[tk] = cost.get(tk, 0.0) + q * p
            shares[tk] = shares.get(tk, 0.0) + q
        elif shares.get(tk, 0) > 0:
            avg = cost[tk] / shares[tk]
            closed += 1
            wins += p > avg
            shares[tk] -= q
            cost[tk] = avg * shares[tk]
    avg_costs = {tk: cost[tk] / shares[tk] for tk in shares if shares[tk] > 1e-6}
    return avg_costs, wins, closed


def average_costs(trades: pd.DataFrame) -> dict:
    """Average purchase price of each stock we still hold."""
    return _replay_cost_basis(trades)[0]


def win_rate(trades: pd.DataFrame):
    """
    Of all the sells, what fraction sold for more than the average price we
    paid? Returns (win_rate or None, number_of_closed_trades).
    """
    _, wins, closed = _replay_cost_basis(trades)
    return (wins / closed if closed else None), closed


# ----- performance ---------------------------------------------------------------

def load_performance() -> pd.DataFrame:
    if not config.PERFORMANCE_CSV.exists():
        return pd.DataFrame(columns=PERF_COLUMNS)
    return pd.read_csv(config.PERFORMANCE_CSV)


def record_performance(date: str, bot_value: float, bot_cash: float,
                       spy_price: float, num_holdings: int) -> pd.DataFrame:
    """
    Add (or replace) today's row in performance.csv.

    Benchmark: on the very first row, we pretend to put $10,000 into SPY at
    that day's price and never touch it. Its value later is simply
    shares_bought_on_day_one * today's SPY price.
    """
    perf = load_performance()
    perf = perf[perf["date"] != date]  # re-running on the same day replaces the row
    if perf.empty:
        spy_shares = config.STARTING_CAPITAL / spy_price
    else:
        spy_shares = config.STARTING_CAPITAL / float(perf.iloc[0]["spy_price"])
    row = pd.DataFrame([{
        "date": date,
        "bot_value": round(bot_value, 2),
        "spy_value": round(spy_shares * spy_price, 2),
        "bot_cash": round(bot_cash, 2),
        "spy_price": round(spy_price, 4),
        "num_holdings": num_holdings,
    }], columns=PERF_COLUMNS)
    perf = pd.concat([perf, row], ignore_index=True) if not perf.empty else row
    perf = perf.sort_values("date").reset_index(drop=True)
    perf.to_csv(config.PERFORMANCE_CSV, index=False)
    return perf


# ----- small state file (remembers when we last rebalanced) ----------------------

def load_state() -> dict:
    if config.STATE_FILE.exists():
        return json.loads(config.STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    config.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    config.STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")
