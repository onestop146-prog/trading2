# Momentum Paper Trading Bot

A simple **momentum** stock bot that runs entirely in the cloud on GitHub Actions
and trades a **paper (fake money) account at Alpaca**. You can manage everything
from your phone.

> 🛑 **PAPER TRADING ONLY.** The bot only ever talks to Alpaca's paper server
> (`https://paper-api.alpaca.markets`, hardcoded in `bot/config.py`). It refuses to run if:
> - the code's trading URL is changed to anything else,
> - an `ALPACA_BASE_URL` / `APCA_API_BASE_URL` setting points anywhere else, or
> - the connected account number doesn't start with `PA` (Alpaca's paper-account prefix).
>
> Also, live-money keys don't work on the paper server at all, so even a mix-up with keys can't reach real money.

**Quick links:** [📊 Live summary](summary.md) · [🧪 Backtest results](backtest/backtest_results.md) ·
[trades.csv](trades.csv) · [performance.csv](performance.csv) · [log](logs/bot.log)

---

## The strategy in plain English

1. **Universe:** the stocks currently in the S&P 500.
2. **Score:** each stock's return from ~12 months ago to ~1 month ago ("12-1 momentum").
   The latest month is skipped because very recent winners tend to dip back short-term.
3. **Hold:** the 10 highest-scoring stocks, equal dollar amounts (~$1,000 each from $10,000).
4. **Rebalance weekly:** Monday ~10:00am Eastern (30 min after the open). Sell stocks that fell out of the
   top 10, buy the new ones. Stocks still in the top 10 are left alone.
   If Monday is a market holiday, it trades on Tuesday instead.
5. **Crash filter:** if SPY (the S&P 500 ETF) is below its 200-day average at rebalance time,
   sell everything and sit in cash until a weekly check finds SPY back above it.

The bot treats **$10,000** as its money even if the paper account has $100,000. It keeps its own books
in `trades.csv` (cash = $10,000 − buys + sells). Fractional shares are used where Alpaca allows them.

**Benchmark:** a pretend $10,000 put into SPY on the bot's first logged day and never touched.

---

## Setup (all from your phone, ~15 minutes)

### Step 1 – Get free Alpaca paper trading keys

1. In your phone's browser go to **alpaca.markets** and tap **Sign Up**. Paper trading is free and only
   needs an email address. You do **not** need to fund anything or open a real brokerage account.
2. Log in. At the top-left of the dashboard, make sure the account switcher says **Paper**
   (it often shows something like "PA3…" — the `PA` means paper). If it shows a live account, switch to Paper.
3. *(Optional but recommended)* Create a **fresh paper account just for this bot** from that same
   account switcher, so nothing else is mixed in with the bot's trades. You can give it a $10,000 balance.
4. On the paper dashboard's home page, find the **API Keys** panel (you may need to scroll down on a phone)
   and tap **Generate New Keys** (or "Regenerate").
5. You'll see two values. Copy both somewhere safe for the next step (e.g. a notes app, temporarily):
   - **API Key ID** (starts with `PK…`)
   - **Secret Key** — ⚠️ shown **only once**. If you lose it, just regenerate.
   The panel should also show the endpoint `https://paper-api.alpaca.markets` — that confirms they're paper keys.

### Step 2 – Add the keys to GitHub Secrets

Secrets are encrypted; they never appear in the code, logs, or commits.

1. Open **github.com** in your phone's **browser** (the GitHub app can't edit secrets).
   If you don't see a **Settings** tab on the repo, use your browser's "Request desktop site" option.
2. Go to this repository → **Settings** → **Secrets and variables** → **Actions**.
3. Tap **New repository secret** and add these two, **names exactly as written**:

   | Name | Value |
   |---|---|
   | `ALPACA_API_KEY` | your API Key ID (`PK…`) |
   | `ALPACA_SECRET_KEY` | your Secret Key |

That's it — only those two secrets. Don't add any URL setting; the paper URL is hardcoded.

### Step 3 – Put the code on the main branch

GitHub only runs **scheduled** workflows from the repository's default branch (`main`).
If this code is on another branch, open a pull request from it into `main` and merge it
(Pull requests → New pull request → pick the branch → Create → Merge).

### Step 4 – Allow the workflows to save files

Repo → **Settings** → **Actions** → **General** → *Workflow permissions* →
choose **Read and write permissions** → Save. (This lets the bot commit `trades.csv` etc.)

### Step 5 – Run the backtest

Repo → **Actions** tab → **Backtest** → **Run workflow**. It takes a few minutes; then open
[`backtest/backtest_results.md`](backtest/backtest_results.md) to see the chart and stats.

### Step 6 – Let it run

Nothing else to do. Automatically:

| Workflow | When (Eastern time) | What it does |
|---|---|---|
| **Weekly rebalance** | Mon ~10:00am (Tue if Monday is a holiday) | Checks crash filter, ranks stocks, places paper orders |
| **Daily performance log** | Weekdays ~4:30–5:30pm | Values the portfolio & SPY benchmark, updates chart + summary (no trading) |
| **Backtest** | When you run it, or when the strategy code changes | Re-runs the historical test |

Want to start trading before next Monday? Actions → **Weekly rebalance** → **Run workflow** →
tick **force** → Run (only works while the market is open, from ~9:55am to 4:00pm ET).

---

## What gets saved to the repo

| File | What's in it |
|---|---|
| `summary.md` | Total return, return vs SPY, max drawdown, win rate, current holdings, chart |
| `performance_chart.png` | Bot vs SPY over time |
| `trades.csv` | Every filled trade: date, ticker, buy/sell, shares, price, value, reason, order id |
| `performance.csv` | One row per trading day: bot value, SPY benchmark value, cash, holdings |
| `logs/bot.log` | Everything the bot did, including any errors and skipped steps |
| `state/bot_state.json` | Last rebalance date, crash filter status, latest top 10 |
| `backtest/` | Backtest chart, results, daily equity and trade list |

---

## Safety and error handling

- **Paper only** — see the box at the top.
- **No duplicate orders.** Every order gets a predictable ID like `mom-20260105-buy-AAPL`. Alpaca won't accept
  a second order with the same ID, and the bot checks for an existing one before placing anything.
  The bot also records the last rebalance date and won't rebalance twice in a day.
- **If data fails to load** (S&P list, prices, SPY), the bot logs it and **does nothing** that run.
  It also stops if fewer than 400 stocks have usable data — that usually means the data source is broken.
- **If an order fails**, it's logged and skipped; the rest carry on. Unfilled orders are cancelled after 90 seconds,
  so nothing is left hanging.
- **Never sells more than it owns**: sells are capped at the shares actually in the paper account.
- **Market holidays** are skipped using Alpaca's market calendar.
- **Late GitHub runs:** GitHub's scheduler can be late. If the rebalance starts more than 5 hours after the open,
  it skips that week rather than trading at a strange time (you can force it manually).

---

## ⚠️ Survivorship bias (read this before trusting the backtest)

The backtest uses **today's** S&P 500 list for the entire history. Those are the companies that *survived and grew*.
Companies that crashed, went bankrupt, or were dropped from the index are missing — so the backtest can never
accidentally buy a future disaster. Momentum strategies are hit especially hard by this, because they buy stocks
that already went up a lot, and some real-world high-flyers later collapsed and left the index.

**Real-world results would very likely be worse than the backtest shows.** Other things a backtest can't capture:
taxes, real fill prices, data errors, and the fact that we picked a strategy already known to have worked in the past.
This is a learning project — not investment advice.

---

## How the code is organized

```
bot/
  config.py         all settings (capital, top N, lookbacks, file names, the hardcoded paper URL)
  alpaca_client.py  paper-only connection to Alpaca + the safety checks
  data.py           S&P 500 list (Wikipedia) and prices (Alpaca, with Yahoo Finance as backup)
  strategy.py       momentum score, crash filter, what to buy/sell (shared with the backtest)
  ledger.py         trades.csv / performance.csv bookkeeping
  report.py         chart + summary.md
  rebalance.py      weekly trading job
  daily.py          daily logging job
backtest/run_backtest.py   historical simulation
tests/test_bot.py          offline tests with fake prices and a fake Alpaca
.github/workflows/         the three scheduled jobs
```

To change the strategy (e.g. hold 20 stocks), edit `bot/config.py`. Pushing that change re-runs the backtest automatically.
