# Comparing settings: more trades vs. returns and risk

_Period 2010-01-05 to 2026-11-19 · daily rebalancing · crash filter on · 0.1% cost per trade · today's S&P 500 list (survivorship bias applies to every row)_

**Closed trades** = a stock bought and later sold. That's what the win rate is measured on, so it's the "sample size" that matters.

| Setting | Trades / year | Closed trades / year | $10,000 became | Yearly return | Max drawdown | Sharpe | Win rate |
|---|---|---|---|---|---|---|---|
| Top 10, 12-1 momentum | 343 | 171 | $861,222 | +30.1% | -43.0% | 1.02 | 51% |
| Top 20, 12-1 momentum | 666 | 332 | $243,521 | +20.7% | -41.9% | 0.85 | 50% |
| Top 30, 12-1 momentum | 959 | 479 | $185,140 | +18.8% | -34.8% | 0.86 | 49% |
| **Top 10, 6-1 momentum (current setting)** | 539 | 269 | $520,222 | +26.1% | -37.1% | 0.96 | 51% |
| Top 10, 3-1 momentum | 764 | 382 | $171,183 | +18.3% | -32.1% | 0.78 | 50% |
| Top 20, 6-1 momentum | 952 | 476 | $167,304 | +18.0% | -38.3% | 0.81 | 49% |
| SPY buy & hold | 0 | 0 | $84,902 | +13.5% | -33.7% | 0.83 | n/a |
| Today's S&P 500, equal weight (bias yardstick) | 0 | 0 | $164,161 | +18.0% | -38.3% | 1.02 | n/a |

- **More stocks** (top 20/30): more trades and more diversification, usually smoother but closer to the market's return.
- **Shorter window** (6-1, 3-1): reacts faster, so it trades a lot more. That's a different, noisier strategy, and the extra trading costs add up.
