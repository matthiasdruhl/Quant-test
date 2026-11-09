# Non-negotiable invariants

These are intended system properties, **not claims that the scaffold currently enforces them all**.

## Temporal correctness
1. All decision-relevant timestamps must be timezone aware; normalize to UTC for storage.
2. A decision at T can depend only on source versions usable no later than T.
3. Record event time, public release time, vendor/source availability time, and our ingestion time separately.
4. Ingestion today does not make a previously published historical fact unavailable in an old simulation, but the historical availability must be established from evidence, not assumed.
5. Economic revisions, restated financials, amended SEC filings, and model-extracted summaries are versioned rather than overwritten.
6. No same-bar closing price used to decide a fill earlier in that bar; signal and fill timestamps must be consistent.
7. Delisted assets and point-in-time membership must not disappear from historical universes.

## Financial accounting
1. Equity = settled/unsettled cash according to declared convention + marked assets - liabilities.
2. Every fill has an immutable unique ID; duplicate notifications do not create duplicate economic events.
3. Fees, spreads, distributions, splits, and execution slippage have explicit conventions and reference tests.
4. Long-only mode may not generate short positions; invalid orders fail without partial state mutation.
5. Cash, holdings, and P&L reconcile from the event ledger under deterministic replay.
6. Price and share units, currency, split adjustments, and sign conventions are explicit.

## Statistical integrity
1. Holdout periods are not repeatedly mined to optimize the strategy.
2. All attempted hypotheses/configurations, including failures, are logged.
3. Baselines, capacity limits, costs, and uncertainty are reported alongside returns.
4. Predictive models use purged/embargoed or otherwise leakage-safe time splits where labels overlap.
5. No strategy is described as profitable without evaluated after-cost out-of-sample evidence.

## Operational and security
1. No real brokerage credentials in repository, test logs, or AI context.
2. Research workers cannot directly call an execution adapter.
3. Any future order path has an independent risk veto and fail-closed behavior.
4. Persist order intent and idempotency key before submit; reconcile after timeout/reconnect.
5. Never silently assume a broker's acknowledged order was filled.
