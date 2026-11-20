# Backtest results: 6-1 momentum (top 10) vs SPY

> ## ⚠️ Survivorship bias warning
> This backtest uses **today's** S&P 500 list for the whole history. Companies that
> collapsed, went bankrupt or were removed from the index are missing, so the strategy
> could never pick a future loser by accident. Momentum strategies are especially
> flattered by this, because they buy stocks that have already risen a lot - and some of
> the real-life winners later crashed and left the index. **Real results would very likely
> have been worse than shown here.** Treat this as an optimistic upper bound, not a forecast.

_Generated 2026-11-20 · Period: 2010-01-05 to 2026-11-19 · Data: 503 of 503 current S&P 500 stocks had data (17.9 years of prices, first year used as warm-up)_

![Backtest chart](backtest_chart.png)

_The chart uses a log scale, so equal vertical distances mean equal % changes._

| | Momentum bot | SPY buy & hold | Today's S&P 500, equal weight* |
|---|---|---|---|
| $10,000 became | $520,222 | $84,902 | $164,161 |
| Total return | +5102% | +749% | +1542% |
| Yearly return (CAGR) | +26.1% | +13.5% | +18.0% |
| Max drawdown | -37.1% | -33.7% | -38.3% |
| Volatility (per year) | 28.3% | 17.1% | 17.9% |
| Sharpe ratio (no risk-free rate) | 0.96 | 0.83 | 1.02 |

\* **Survivorship-bias yardstick:** simply owning *all* of today's S&P 500 members in equal
amounts, with no strategy. Its lead over SPY (+4.5% per year) is roughly how much the survivor list alone flatters
results. The bot's lead over **this** column (+8.1% per year) is a fairer (still optimistic) guess at what momentum adds.

- **Return vs SPY:** +4353% total, +12.6% per year
- **Win rate:** 51% of 4542 closed trades sold above their purchase price
- **Right now** the bot is 30% below its all-time high in this backtest (0% = at a new high)
- **Time spent in cash** (crash filter): 16% of trading days
- **Trades:** 9094 total; assumed 0.1% slippage per trade, no commissions

## Daily vs weekly rebalancing

The bot is set to **daily** (change `REBALANCE_FREQUENCY` in `bot/config.py`). Same rules, same data, only how often it checks:

| Rebalance | $10,000 became | Yearly return | Max drawdown | Trades |
|---|---|---|---|---|
| daily | $520,222 | +26.1% | -37.1% | 9,094 |
| weekly | $765,558 | +29.3% | -36.1% | 3,910 |

_Daily checks react faster to the crash filter and to new leaders, but trade more, and each trade costs an assumed 0.1%._

## Year by year

| Year | Bot | SPY | Difference |
|---|---|---|---|
| 2010 | +6.0% | +13.2% | -7.2% |
| 2011 | -9.1% | +1.9% | -11.0% |
| 2012 | +14.0% | +16.0% | -2.0% |
| 2013 | +55.8% | +32.3% | +23.5% |
| 2014 | +12.6% | +13.5% | -0.9% |
| 2015 | +13.4% | +1.2% | +12.2% |
| 2016 | +28.3% | +12.0% | +16.3% |
| 2017 | +38.2% | +21.7% | +16.5% |
| 2018 | +31.7% | -4.6% | +36.3% |
| 2019 | +14.6% | +31.2% | -16.6% |
| 2020 | +53.9% | +18.3% | +35.6% |
| 2021 | +14.5% | +28.7% | -14.2% |
| 2022 | -14.8% | -18.2% | +3.3% |
| 2023 | +33.1% | +26.2% | +6.9% |
| 2024 | +83.9% | +24.9% | +59.0% |
| 2025 | +44.4% | +17.7% | +26.7% |
| 2026 | +67.7% | +5.8% | +61.9% |

## How the backtest works

- Universe: today's S&P 500 members (see warning above).
- Rebalance daily: rank stocks by the return from ~6 months ago to ~1 month ago, using prices up to the previous close.
- Hold the top 10, equal weight. Only stocks that drop out of the top 10 are sold; new entries are bought at the opening price.
- Crash filter: if SPY closed below its 200-day average, sell everything and wait in cash.
- Prices are adjusted for splits and dividends (dividends are effectively reinvested).
- Other things a backtest can't capture: taxes, real fill prices, data errors, and the fact that the strategy rules were picked knowing momentum worked in the past.

Files: [daily equity](backtest_equity.csv) · [all trades](backtest_trades.csv)
