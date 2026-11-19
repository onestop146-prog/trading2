"""
A tiny, PAPER-ONLY wrapper around Alpaca's REST API.

Why not use Alpaca's official Python SDK? Because writing the few calls we
need by hand keeps things transparent, and lets us *guarantee* that every
trading request goes to the paper server: the URL is built from the hardcoded
constant in config.py and nothing else.

Safety layers (any one of them failing stops the bot):
  1. The hardcoded URL must be the paper server.
  2. If someone sets an ALPACA_BASE_URL / APCA_API_BASE_URL environment
     variable to anything other than the paper server, we refuse to run.
  3. After connecting, we ask Alpaca for the account details and check the
     account number starts with "PA" (Alpaca's prefix for paper accounts).
Also: live-money API keys do not work on the paper server at all, so even
if live keys were accidentally saved as secrets, the paper server would
simply reject them.
"""

import os
import time

import requests

from bot import config
from bot.log import get_logger

log = get_logger()


class PaperOnlyError(RuntimeError):
    """Raised when anything suggests we might be talking to a real-money account."""


def _check_paper_url() -> None:
    """Safety layers 1 and 2: make sure only the paper URL is ever used."""
    url = config.PAPER_TRADING_URL.rstrip("/")
    if url != "https://paper-api.alpaca.markets":
        raise PaperOnlyError(f"Trading URL {url!r} is not Alpaca's paper server. Refusing to run.")

    for var in ("ALPACA_BASE_URL", "APCA_API_BASE_URL", "ALPACA_ENDPOINT"):
        value = os.environ.get(var, "").strip().rstrip("/")
        if value and value != url and value != url + "/v2":
            raise PaperOnlyError(
                f"Environment variable {var}={value!r} points somewhere other than the "
                f"paper server ({url}). This bot only paper trades. Refusing to run."
            )


class AlpacaPaper:
    """Talks to Alpaca's paper trading API and market-data API."""

    def __init__(self) -> None:
        _check_paper_url()

        key = os.environ.get("ALPACA_API_KEY", "").strip()
        secret = os.environ.get("ALPACA_SECRET_KEY", "").strip()
        if not key or not secret:
            raise RuntimeError(
                "Missing ALPACA_API_KEY / ALPACA_SECRET_KEY. Add them as GitHub Secrets "
                "(see README.md)."
            )

        self.session = requests.Session()
        self.session.headers.update({
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
        })

        # Safety layer 3: confirm this really is a paper account.
        account = self.get_account()
        account_number = str(account.get("account_number", ""))
        if not account_number.startswith("PA"):
            raise PaperOnlyError(
                f"Account number {account_number!r} does not look like a paper account "
                "(paper accounts start with 'PA'). Refusing to run."
            )
        log.info("Connected to Alpaca PAPER account %s...%s",
                 account_number[:3], account_number[-2:])

    # ----- low-level helpers -------------------------------------------------

    def _trading(self, method: str, path: str, **kwargs):
        """Send a request to the PAPER trading server. The base URL is fixed."""
        url = config.PAPER_TRADING_URL + path
        resp = self.session.request(method, url, timeout=30, **kwargs)
        return resp

    def _trading_json(self, method: str, path: str, **kwargs):
        resp = self._trading(method, path, **kwargs)
        resp.raise_for_status()
        return resp.json() if resp.content else None

    def _data_json(self, path: str, params: dict):
        """Market data (prices). This server cannot place orders."""
        url = config.MARKET_DATA_URL + path
        resp = self.session.get(url, params=params, timeout=60)
        resp.raise_for_status()
        return resp.json()

    # ----- account / market info ----------------------------------------------

    def get_account(self) -> dict:
        return self._trading_json("GET", "/v2/account")

    def get_clock(self) -> dict:
        """Is the market open right now? Includes next open/close times."""
        return self._trading_json("GET", "/v2/clock")

    def get_calendar(self, start: str, end: str) -> list:
        """Trading days between two dates (YYYY-MM-DD). Holidays are simply missing."""
        return self._trading_json("GET", "/v2/calendar", params={"start": start, "end": end})

    def get_positions(self) -> dict:
        """What the paper account actually holds: {symbol: shares}."""
        positions = self._trading_json("GET", "/v2/positions")
        return {p["symbol"]: float(p["qty"]) for p in positions}

    def get_asset(self, symbol: str):
        """Info about a stock, e.g. whether it's tradable and whether we can buy
        fractions of a share. Returns None if Alpaca doesn't know the symbol."""
        resp = self._trading("GET", f"/v2/assets/{symbol}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    # ----- orders --------------------------------------------------------------

    def find_order_by_client_id(self, client_order_id: str):
        """Return an existing order with this ID, or None. Used to avoid duplicates."""
        resp = self._trading("GET", "/v2/orders:by_client_order_id",
                             params={"client_order_id": client_order_id})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def submit_market_order(self, symbol: str, qty: float, side: str, client_order_id: str) -> dict:
        """
        Place a market order. `client_order_id` is a unique name we choose,
        e.g. "mom-20250106-buy-AAPL". Alpaca refuses a second order with the
        same name, which is our protection against duplicate orders.
        """
        assert side in ("buy", "sell")
        assert qty > 0
        body = {
            "symbol": symbol,
            "qty": f"{qty:.6f}".rstrip("0").rstrip("."),
            "side": side,
            "type": "market",
            "time_in_force": "day",  # required for fractional shares
            "client_order_id": client_order_id,
        }
        return self._trading_json("POST", "/v2/orders", json=body)

    def get_order(self, order_id: str) -> dict:
        return self._trading_json("GET", f"/v2/orders/{order_id}")

    def cancel_order(self, order_id: str) -> None:
        resp = self._trading("DELETE", f"/v2/orders/{order_id}")
        if resp.status_code not in (200, 204, 404, 422):
            resp.raise_for_status()

    def wait_for_fill(self, order: dict, timeout_seconds: int = 90) -> dict:
        """
        Check the order every few seconds until it's done. If it still isn't
        filled after `timeout_seconds`, cancel whatever is left so nothing is
        left hanging around.
        """
        done = {"filled", "canceled", "expired", "rejected", "done_for_day"}
        deadline = time.time() + timeout_seconds
        while order.get("status") not in done and time.time() < deadline:
            time.sleep(3)
            order = self.get_order(order["id"])
        if order.get("status") not in done:
            log.warning("Order %s not filled in time; cancelling the rest.", order.get("client_order_id"))
            self.cancel_order(order["id"])
            time.sleep(3)
            order = self.get_order(order["id"])
        return order

    # ----- prices ----------------------------------------------------------------

    def get_latest_prices(self, symbols: list) -> dict:
        """Most recent trade price for each symbol (IEX feed, free)."""
        prices = {}
        for i in range(0, len(symbols), 100):
            chunk = symbols[i:i + 100]
            data = self._data_json("/v2/stocks/trades/latest",
                                   {"symbols": ",".join(chunk), "feed": "iex"})
            for sym, trade in data.get("trades", {}).items():
                if trade and trade.get("p"):
                    prices[sym] = float(trade["p"])
        return prices

    def get_daily_bars(self, symbols: list, start: str, end: str) -> dict:
        """
        Daily price bars, adjusted for splits and dividends.
        Returns {symbol: [(date_string, open, close), ...]}.
        Free accounts may request full-market ("sip") data as long as it is
        at least 15 minutes old, so callers should pass an `end` in the past.
        """
        out = {}
        for i in range(0, len(symbols), 100):
            chunk = symbols[i:i + 100]
            page_token = None
            while True:
                params = {
                    "symbols": ",".join(chunk),
                    "timeframe": "1Day",
                    "start": start,
                    "end": end,
                    "adjustment": "all",
                    "feed": "sip",
                    "limit": 10000,
                }
                if page_token:
                    params["page_token"] = page_token
                data = self._data_json("/v2/stocks/bars", params)
                for sym, bars in (data.get("bars") or {}).items():
                    out.setdefault(sym, []).extend(
                        (b["t"][:10], float(b["o"]), float(b["c"])) for b in bars
                    )
                page_token = data.get("next_page_token")
                if not page_token:
                    break
        return out
