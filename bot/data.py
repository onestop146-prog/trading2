"""
Getting data: the list of S&P 500 stocks, and their daily prices.

Two price sources are supported, and if one fails we try the other:
  * Alpaca market data (needs your API keys; history starts in 2016)
  * Yahoo Finance via the `yfinance` package (no keys; long history, but it
    sometimes rate-limits cloud servers like GitHub Actions)

Prices are "adjusted": past prices are corrected for stock splits and
dividends, so a 2-for-1 split doesn't look like a 50% crash.
"""

import io
import time

import pandas as pd
import requests

from bot import config
from bot.log import get_logger

log = get_logger()

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


# ---------------------------------------------------------------------------
# The universe: today's S&P 500 list
# ---------------------------------------------------------------------------

def get_sp500_tickers() -> list:
    """
    Download today's S&P 500 list from Wikipedia. If that fails, fall back to
    the copy saved in data/sp500_tickers.csv from the last successful download.
    Tickers use Alpaca's style, e.g. "BRK.B".
    """
    try:
        html = requests.get(WIKI_URL, timeout=30,
                            headers={"User-Agent": "Mozilla/5.0 (momentum-paper-bot)"}).text
        table = pd.read_html(io.StringIO(html))[0]
        tickers = sorted(table["Symbol"].astype(str).str.strip().str.replace("-", ".").unique())
        if len(tickers) < 450:  # sanity check: the page layout may have changed
            raise ValueError(f"only found {len(tickers)} tickers")
        config.SP500_CACHE.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({"ticker": tickers}).to_csv(config.SP500_CACHE, index=False)
        log.info("Downloaded S&P 500 list: %d tickers", len(tickers))
        return tickers
    except Exception as exc:
        log.warning("Could not download S&P 500 list (%s); using saved copy.", exc)
        if config.SP500_CACHE.exists():
            return pd.read_csv(config.SP500_CACHE)["ticker"].tolist()
        raise RuntimeError("No S&P 500 list available (download failed and no saved copy).")


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------

def _from_yahoo(symbols: list, start: str, end: str):
    """Download adjusted daily open & close prices from Yahoo Finance."""
    import yfinance as yf

    to_yahoo = {s: s.replace(".", "-") for s in symbols}   # BRK.B -> BRK-B
    from_yahoo = {v: k for k, v in to_yahoo.items()}
    opens, closes = [], []
    for i in range(0, len(symbols), 100):                  # 100 at a time
        chunk = [to_yahoo[s] for s in symbols[i:i + 100]]
        df = yf.download(chunk, start=start, end=end, auto_adjust=True,
                         progress=False, threads=True, group_by="column")
        if df is None or df.empty:
            continue
        opens.append(df["Open"])
        closes.append(df["Close"])
        time.sleep(1)  # be polite to Yahoo
    if not closes:
        raise RuntimeError("Yahoo returned no data")
    o = pd.concat(opens, axis=1).rename(columns=from_yahoo)
    c = pd.concat(closes, axis=1).rename(columns=from_yahoo)
    return o, c


def _from_alpaca(symbols: list, start: str, end: str, client=None):
    """Download adjusted daily open & close prices from Alpaca."""
    if client is None:
        from bot.alpaca_client import AlpacaPaper
        client = AlpacaPaper()
    # Free data plans need the end time to be 15+ minutes in the past.
    latest_allowed = pd.Timestamp.now(tz="UTC") - pd.Timedelta(minutes=20)
    end_ts = min(pd.Timestamp(end, tz="UTC"), latest_allowed)
    bars = client.get_daily_bars(symbols, start=start, end=end_ts.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if not bars:
        raise RuntimeError("Alpaca returned no data")
    o = pd.DataFrame({s: pd.Series({d: op for d, op, _ in rows}) for s, rows in bars.items()})
    c = pd.DataFrame({s: pd.Series({d: cl for d, _, cl in rows}) for s, rows in bars.items()})
    return o, c


def get_prices(symbols: list, start: str, end: str, prefer: str = "alpaca", client=None):
    """
    Returns two tables (opens, closes): one row per trading day, one column
    per ticker. Tries the preferred source first, then the other one.
    Tickers with no data at all are dropped.
    """
    sources = ["alpaca", "yahoo"] if prefer == "alpaca" else ["yahoo", "alpaca"]
    errors = []
    for source in sources:
        try:
            if source == "alpaca":
                o, c = _from_alpaca(symbols, start, end, client)
            else:
                o, c = _from_yahoo(symbols, start, end)
            for df in (o, c):
                df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
            o, c = o.sort_index(), c.sort_index()
            c = c.dropna(axis=1, how="all")
            o = o.reindex(columns=c.columns)
            log.info("Loaded prices from %s: %d tickers, %d days (%s to %s)", source,
                     c.shape[1], c.shape[0], c.index.min().date(), c.index.max().date())
            return o, c
        except Exception as exc:
            log.warning("Price download from %s failed: %s", source, exc)
            errors.append(f"{source}: {exc}")
    raise RuntimeError("All price sources failed: " + " | ".join(errors))
