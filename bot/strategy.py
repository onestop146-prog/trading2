"""
The momentum strategy itself. Both the backtest and the live bot use these
exact functions, so what you see in the backtest is what the bot does.

"12-1 momentum": for each stock, measure the return from ~12 months ago to
~1 month ago. The most recent month is skipped because, historically, stocks
that jumped in the last few weeks tend to fall back a little short-term
(a well-known effect called "short-term reversal").
"""

import pandas as pd

from bot import config


def momentum_scores(closes: pd.DataFrame) -> pd.Series:
    """
    `closes` has one row per trading day (oldest first) and one column per
    stock, and must END on the most recent day we know about.

    Score = price 1 month ago / price 12 months ago - 1
    Stocks without enough history get no score.
    """
    needed = config.LOOKBACK_DAYS + 1
    if len(closes) < needed:
        return pd.Series(dtype=float)
    price_1m_ago = closes.iloc[-1 - config.SKIP_DAYS]
    price_12m_ago = closes.iloc[-1 - config.LOOKBACK_DAYS]
    scores = price_1m_ago / price_12m_ago - 1
    return scores.dropna().sort_values(ascending=False)


def top_stocks(closes: pd.DataFrame, n: int = config.TOP_N) -> list:
    """The n stocks with the highest momentum score, best first."""
    return momentum_scores(closes).head(n).index.tolist()


def market_is_healthy(spy_closes: pd.Series):
    """
    Crash filter. Returns (healthy, spy_price, spy_200_day_average).
    healthy is True when SPY is ABOVE its 200-day moving average.
    Returns healthy=None if there isn't enough data to decide.
    """
    spy = spy_closes.dropna()
    if len(spy) < config.SMA_DAYS:
        return None, None, None
    price = float(spy.iloc[-1])
    sma = float(spy.iloc[-config.SMA_DAYS:].mean())
    return price > sma, price, sma


def plan_rebalance(holdings: dict, targets: list, healthy: bool):
    """
    Decide what to sell and what to buy. Pure logic, no trading.

    holdings: {ticker: shares} we currently own
    targets:  today's top-N tickers
    healthy:  result of the crash filter

    Returns (sells, buys):
      sells = [(ticker, reason), ...]
      buys  = [ticker, ...] in rank order
    Stocks still in the top N are left alone (no trading needed).
    """
    if not healthy:
        reason = "crash filter: SPY below 200-day average"
        return [(t, reason) for t in holdings], []

    sells = [(t, f"dropped out of top {config.TOP_N}") for t in holdings if t not in targets]
    keep = [t for t in holdings if t in targets]
    open_slots = config.TOP_N - len(keep)
    buys = [t for t in targets if t not in holdings][:max(open_slots, 0)]
    return sells, buys
