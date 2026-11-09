# Incremental roadmap and definition of done

Estimated timing is optional; **gates are evidence-based**. Do not treat checkboxes as completed until demonstrated in CI and review.

## M0 — Governance and skeleton (current)
- [x] Versioned architecture, source boundaries, temporal and trading contracts.
- [x] Minimal installable Python package and CI configuration.
- [x] One tested time-availability primitive and explicit unimplemented modules.
- [ ] CI has actually run successfully on GitHub.
- [ ] Repo protection/rulesets are configured by owner (where available).

## M1 — Point-in-time market data
- [ ] Security master with delisting/history.
- [ ] Licensed OHLCV, corporate actions, data provenance and replay fixtures.
- [ ] Source availability is tested against decision timestamps.
- [ ] Reproducible dataset snapshots, null/quality reporting.

## M2 — Backtester and accounting
- [ ] Reference ledger scenarios pass.
- [ ] Costs, partial fills, sessions, splits, and dividends tested.
- [ ] Future-data trap tests fail correctly.
- [ ] Runs reproducible by configuration and dataset revision.

## M3 — Strategy and statistical evaluation
- [ ] Simple momentum/reversion baselines, no invented P&L.
- [ ] Benchmark, chronological validation, holdout controls.
- [ ] Store all failed and successful experiments.
- [ ] Quantify uncertainty and trading cost sensitivity.

## M4 — AI research assistance
- [ ] Bounded proposal/implementation/reviewer workflow.
- [ ] No credential, deployment, or trading permissions.
- [ ] Research outputs have reproducible experiment IDs.

## M5 — Macro and event intelligence
- [ ] Release/consensus/revision timestamps and provenance verified.
- [ ] External features evaluated against technical-only baselines.
- [ ] Contradictory sources and missing information flagged.

## M6 — SEC and public disclosures
- [ ] Form 4 and 13F parsing, amendment chains, lag-aware features.
- [ ] Political disclosures only after permitted-use review.
- [ ] Source links and uncertainty are visible.

## M7 — Paper trading
- [ ] Broker adapter isolated from research code.
- [ ] Idempotent order state and account reconciliation.
- [ ] Independent veto, emergency stop, failure drills.
- [ ] Forward signals tracked long enough to assess viability.

## M8 — Alternative data
- [ ] License-aware ingest, quality/coverage tests.
- [ ] Small satellite or physical-activity proof of concept.
- [ ] Demonstrated incremental forecast value, including acquisition cost.

## M9 — Future controlled deployment
- [ ] Owner approval and live-specific threat model.
- [ ] Forward tested edge and tolerable loss profile.
- [ ] Broker restrictions, security review, monitoring and incident response.
- [ ] Conservative capital limits; do not assume income targets are guaranteed.
