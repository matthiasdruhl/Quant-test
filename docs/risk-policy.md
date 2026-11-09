# Risk policy (pre-live draft)

**This document authorizes no trades.** There is currently no order execution implementation.

Before any paper trading, define:
- Maximum notional and percent-of-equity per security and sector.
- Portfolio gross and net exposure, correlation, and liquidity caps.
- Drawdown monitoring (including intraday and overnight gaps).
- Order rate limits, limit/market order rules, stale quote checks.
- Reconciliation on startup, reconnect, and before any order.
- Behavior on stale data, broker outages, timeouts, partial fills, and API errors.
- Manual emergency stop and default-deny permission model.
- Proven actual ingestion and processing times for operational inputs; historical source eligibility alone is insufficient.
- Target expiry handling, pending-order treatment, and invalid-batch rejection under the strategy contract; stale targets cannot create new orders.

Limits must be enforced by deterministic portfolio/risk code, outside AI agent control. A model's reported confidence or expected return never overrides policy. Stops are not guarantees against gapping markets or broker failures.

A future funded-account module must model firm-specific restrictions separately from investment strategy research, including simulated/live status, payout costs, daily and trailing drawdown rules, and overnight limits.
