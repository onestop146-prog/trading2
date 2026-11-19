# Backtest results: 12-1 momentum vs SPY

> ## ⚠️ Survivorship bias warning
> This backtest uses **today's** S&P 500 list for the whole history. Companies that
> collapsed, went bankrupt or were removed from the index are missing, so the strategy
> could never pick a future loser by accident. Momentum strategies are especially
> flattered by this, because they buy stocks that have already risen a lot - and some of
> the real-life winners later crashed and left the index. **Real results would very likely
> have been worse than shown here.** Treat this as an optimistic upper bound, not a forecast.

_Generated 2026-11-19 · Period: 2010-01-05 to 2026-11-19 · Data: 503 of 503 current S&P 500 stocks had data (17.9 years of prices, first year used as warm-up)_

![Backtest chart](backtest_chart.png)

_The chart uses a log scale, so equal vertical distances mean equal % changes._

| | Momentum bot | SPY buy & hold |
|---|---|---|
| $10,000 became | $852,626 | $85,126 |
| Total return | +8426% | +751% |
| Yearly return (CAGR) | +30.2% | +13.5% |
| Max drawdown | -46.3% | -33.7% |
| Volatility (per year) | 30.5% | 17.1% |
| Sharpe ratio (no risk-free rate) | 1.02 | 0.83 |

- **Return vs SPY:** +7675% total, +16.6% per year
- **Win rate:** 53% of 1323 closed trades sold above their purchase price
- **Time spent in cash** (crash filter): 16% of trading days
- **Trades:** 2656 total; assumed 0.1% slippage per trade, no commissions

## Year by year

| Year | Bot | SPY | Difference |
|---|---|---|---|
| 2010 | +12.4% | +13.2% | -0.8% |
| 2011 | -1.7% | +1.9% | -3.6% |
| 2012 | +47.8% | +16.0% | +31.8% |
| 2013 | +60.7% | +32.3% | +28.4% |
| 2014 | +16.4% | +13.5% | +2.9% |
| 2015 | -0.9% | +1.2% | -2.1% |
| 2016 | +39.5% | +12.0% | +27.5% |
| 2017 | +40.5% | +21.7% | +18.8% |
| 2018 | +7.9% | -4.6% | +12.4% |
| 2019 | +16.9% | +31.2% | -14.3% |
| 2020 | +80.7% | +18.3% | +62.4% |
| 2021 | +10.7% | +28.7% | -18.1% |
| 2022 | -6.3% | -18.2% | +11.9% |
| 2023 | +30.1% | +26.2% | +4.0% |
| 2024 | +137.1% | +24.9% | +112.2% |
| 2025 | +57.6% | +17.7% | +39.9% |
| 2026 | +25.0% | +6.1% | +19.0% |

## How the backtest works

- Universe: today's S&P 500 members (see warning above).
- Every week on the first trading day: rank stocks by the return from ~12 months ago to ~1 month ago, using prices up to the previous close.
- Hold the top 10, equal weight. Only stocks that drop out of the top 10 are sold; new entries are bought at the opening price.
- Crash filter: if SPY closed below its 200-day average, sell everything and wait in cash.
- Prices are adjusted for splits and dividends (dividends are effectively reinvested).
- Other things a backtest can't capture: taxes, real fill prices, data errors, and the fact that the strategy rules were picked knowing momentum worked in the past.

Files: [daily equity](backtest_equity.csv) · [all trades](backtest_trades.csv)
