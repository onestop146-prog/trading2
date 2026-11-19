"""
Tests that run without internet or API keys, using made-up prices and a
fake Alpaca client. Run with:   python -m pytest -q
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from bot import alpaca_client, config, ledger, rebalance, strategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def temp_files(tmp_path, monkeypatch):
    """Point all output files at a temporary folder so tests don't touch the repo."""
    for name, fname in [("TRADES_CSV", "trades.csv"), ("PERFORMANCE_CSV", "performance.csv"),
                        ("SUMMARY_MD", "summary.md"), ("CHART_PNG", "chart.png"),
                        ("STATE_FILE", "state.json"), ("SP500_CACHE", "sp500.csv"),
                        ("BACKTEST_DIR", "bt")]:
        monkeypatch.setattr(config, name, tmp_path / fname)
    return tmp_path


def fake_prices(n_stocks=450, n_days=600, spy_trend=0.0004, seed=1):
    """Random-walk prices; stock i has a slightly different built-in drift."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=n_days)
    drifts = np.linspace(-0.001, 0.002, n_stocks)
    rets = rng.normal(drifts, 0.015, size=(n_days, n_stocks))
    closes = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=dates,
                          columns=[f"S{i:03d}" for i in range(n_stocks)])
    closes["SPY"] = 400 * np.exp(np.cumsum(rng.normal(spy_trend, 0.01, n_days)))
    opens = closes.shift(1).fillna(closes)
    return opens, closes


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

def test_momentum_skips_last_month():
    dates = pd.bdate_range("2020-01-01", periods=300)
    a = pd.Series(100.0, index=dates)
    b = pd.Series(100.0, index=dates)
    b.iloc[-10:] = 1000.0            # B jumps only in the LAST month -> ignored
    a.iloc[-100:] = 150.0            # A rose 50% in the months before that
    scores = strategy.momentum_scores(pd.DataFrame({"A": a, "B": b}))
    assert scores.index[0] == "A"
    assert scores["B"] == pytest.approx(0.0)
    assert scores["A"] == pytest.approx(0.5)


def test_crash_filter():
    up = pd.Series(np.linspace(100, 200, 250))
    down = pd.Series(np.linspace(200, 100, 250))
    assert strategy.market_is_healthy(up)[0] is True
    assert strategy.market_is_healthy(down)[0] is False
    assert strategy.market_is_healthy(up[:50])[0] is None


def test_plan_rebalance():
    holdings = {"A": 1, "B": 1, "C": 1}
    targets = ["A", "X", "Y", "B"]
    sells, buys = strategy.plan_rebalance(holdings, targets, healthy=True)
    assert [s for s, _ in sells] == ["C"]
    assert buys == ["X", "Y"]
    sells, buys = strategy.plan_rebalance(holdings, targets, healthy=False)
    assert sorted(s for s, _ in sells) == ["A", "B", "C"] and buys == []


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

def test_ledger_replay_and_win_rate():
    ledger.record_trade("2025-01-06", "AAA", "buy", 10, 100, "entered")
    ledger.record_trade("2025-01-06", "BBB", "buy", 5, 200, "entered")
    ledger.record_trade("2025-01-13", "AAA", "sell", 10, 110, "dropped")
    ledger.record_trade("2025-01-20", "BBB", "sell", 5, 150, "dropped")
    ledger.record_trade("2025-01-20", "CCC", "buy", 2, 50, "entered")
    trades = ledger.load_trades()
    holdings, cash = ledger.holdings_and_cash(trades)
    assert holdings == {"CCC": 2}
    assert cash == pytest.approx(10_000 - 1000 - 1000 + 1100 + 750 - 100)
    assert ledger.win_rate(trades) == (0.5, 2)
    assert ledger.average_costs(trades) == {"CCC": 50}


def test_benchmark_is_fixed_on_day_one():
    ledger.record_performance("2025-01-06", 10_000, 10_000, 500.0, 0)
    perf = ledger.record_performance("2025-01-07", 10_100, 0, 550.0, 10)
    assert perf.iloc[-1]["spy_value"] == pytest.approx(11_000)
    perf = ledger.record_performance("2025-01-07", 10_100, 0, 540.0, 10)  # re-run same day
    assert len(perf) == 2 and perf.iloc[-1]["spy_value"] == pytest.approx(10_800)


# ---------------------------------------------------------------------------
# Paper-only safety
# ---------------------------------------------------------------------------

def test_refuses_live_endpoint_env(monkeypatch):
    monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
    with pytest.raises(alpaca_client.PaperOnlyError):
        alpaca_client._check_paper_url()


def test_refuses_edited_url(monkeypatch):
    monkeypatch.setattr(config, "PAPER_TRADING_URL", "https://api.alpaca.markets")
    with pytest.raises(alpaca_client.PaperOnlyError):
        alpaca_client._check_paper_url()


def test_refuses_non_paper_account(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "x")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "y")
    monkeypatch.setattr(alpaca_client.AlpacaPaper, "get_account",
                        lambda self: {"account_number": "123456789"})
    with pytest.raises(alpaca_client.PaperOnlyError):
        alpaca_client.AlpacaPaper()


# ---------------------------------------------------------------------------
# Backtest (synthetic data)
# ---------------------------------------------------------------------------

def test_backtest_runs():
    from backtest import run_backtest
    opens, closes = fake_prices()
    equity, trades = run_backtest.run_backtest(opens, closes)
    assert len(equity) == len(closes) - 253
    assert equity["num_holdings"].max() == config.TOP_N
    assert (equity["bot_value"] > 0).all()
    run_backtest.write_results(equity, trades, "synthetic")
    assert (config.BACKTEST_DIR / "backtest_chart.png").exists()
    assert "Survivorship" in (config.BACKTEST_DIR / "backtest_results.md").read_text()


# ---------------------------------------------------------------------------
# Live rebalance with a fake Alpaca
# ---------------------------------------------------------------------------

class FakeAlpaca:
    """Pretends to be Alpaca: fills every market order instantly at `prices`."""

    def __init__(self, prices, today):
        self.prices, self.today = prices, today
        self.orders = {}       # client_order_id -> order
        self.positions = {}

    def get_calendar(self, start, end):
        return [{"date": self.today, "open": "09:30", "close": "16:00"}]

    def get_clock(self):
        return {"is_open": True}

    def get_positions(self):
        return dict(self.positions)

    def get_asset(self, symbol):
        return {"tradable": True, "fractionable": True}

    def get_latest_prices(self, symbols):
        return {s: self.prices[s] for s in symbols}

    def find_order_by_client_id(self, cid):
        return self.orders.get(cid)

    def submit_market_order(self, symbol, qty, side, cid):
        assert cid not in self.orders, "duplicate order!"
        px = self.prices[symbol]
        order = {"id": f"id-{cid}", "client_order_id": cid, "status": "filled",
                 "filled_qty": str(qty), "filled_avg_price": str(px)}
        self.orders[cid] = order
        sign = 1 if side == "buy" else -1
        self.positions[symbol] = self.positions.get(symbol, 0) + sign * qty
        return order

    def wait_for_fill(self, order):
        return order


def test_rebalance_end_to_end(monkeypatch):
    opens, closes = fake_prices(spy_trend=0.001)
    today_dt = closes.index[-1] + pd.offsets.BDay(1)
    today = today_dt.date().isoformat()
    fake = FakeAlpaca({c: float(closes[c].iloc[-1]) for c in closes.columns}, today)

    monkeypatch.setattr(rebalance, "AlpacaPaper", lambda: fake)
    monkeypatch.setattr(rebalance.data, "get_sp500_tickers",
                        lambda: [c for c in closes.columns if c != "SPY"])
    monkeypatch.setattr(rebalance.data, "get_prices", lambda *a, **k: (opens, closes))

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(f"{today}T10:00:00").replace(tzinfo=ZoneInfo("America/New_York"))
    monkeypatch.setattr(rebalance, "datetime", FakeDatetime)

    assert rebalance.run() == 0
    trades = ledger.load_trades()
    holdings, cash = ledger.holdings_and_cash(trades)
    assert len(holdings) == config.TOP_N
    assert set(holdings) == set(strategy.top_stocks(closes.drop(columns="SPY")))
    assert 0 <= cash < 0.02 * config.STARTING_CAPITAL      # nearly fully invested
    invested = sum(q * fake.prices[t] for t, q in holdings.items())
    assert invested == pytest.approx(config.STARTING_CAPITAL * 0.99, rel=0.01)

    # Running again the same day must NOT place any more orders
    n_orders = len(fake.orders)
    assert rebalance.run() == 0
    assert len(fake.orders) == n_orders
    assert len(ledger.load_trades()) == len(trades)

    # Even if the state file is lost, the predictable order IDs prevent duplicates
    config.STATE_FILE.unlink()
    assert rebalance.run() == 0
    assert len(fake.orders) == n_orders
    assert len(ledger.load_trades()) == len(trades)


def test_rebalance_skips_when_data_fails(monkeypatch):
    today = "2025-01-06"
    fake = FakeAlpaca({}, today)
    monkeypatch.setattr(rebalance, "AlpacaPaper", lambda: fake)
    monkeypatch.setattr(rebalance.data, "get_sp500_tickers", lambda: ["AAA"])

    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(rebalance.data, "get_prices", boom)

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2025, 1, 6, 10, 0, tzinfo=ZoneInfo("America/New_York"))
    monkeypatch.setattr(rebalance, "datetime", FakeDatetime)

    assert rebalance.run() == 0
    assert fake.orders == {}
    assert not config.TRADES_CSV.exists()


def test_daily_log_and_report(monkeypatch):
    from bot import daily
    opens, closes = fake_prices(n_stocks=20, n_days=30)
    today = closes.index[-1].date().isoformat()
    ledger.record_trade(today, "S001", "buy", 10, float(closes["S001"].iloc[-2]), "entered")
    fake = FakeAlpaca({}, today)
    fake.get_clock = lambda: {"is_open": False}
    monkeypatch.setattr(daily, "AlpacaPaper", lambda: fake)
    monkeypatch.setattr(daily.data, "get_prices", lambda *a, **k: (opens, closes))

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromisoformat(f"{today}T17:30:00").replace(tzinfo=ZoneInfo("America/New_York"))
    monkeypatch.setattr(daily, "datetime", FakeDatetime)

    assert daily.run() == 0
    perf = ledger.load_performance()
    assert len(perf) == 1 and perf.iloc[0]["spy_value"] == pytest.approx(10_000)
    expected = 10_000 - 10 * closes["S001"].iloc[-2] + 10 * closes["S001"].iloc[-1]
    assert perf.iloc[0]["bot_value"] == pytest.approx(expected, abs=0.01)
    summary = config.SUMMARY_MD.read_text()
    assert "S001" in summary and "Max drawdown" in summary
    assert config.CHART_PNG.exists()
