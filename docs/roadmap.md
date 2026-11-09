# Incremental roadmap and definition of done

Estimated timing is optional; **gates are evidence-based**. Do not treat checkboxes as completed until demonstrated in CI and independent owner/reviewer review. Every completed gate must link to its immutable source revision, CI run (where executable), acceptance results, and review record in the PR or an evidence record. For a manual gate, record the owner, date, and verifiable outcome. Missing evidence leaves the box unchecked. Agents may report local checks but cannot invent CI/review approval or promote a milestone.

## M0 — Governance and skeleton (current)
- [ ] Versioned architecture, source boundaries, temporal and trading contracts accepted in review.
- [ ] Minimal installable Python package and hash-locked CI configuration verified.
- [ ] Time-availability primitive and explicit unimplemented modules verified in CI/review.
- [ ] CI has actually run successfully on GitHub.
- [ ] Repo protection/rulesets are configured by owner (where available).

The contracts, package, workflow, and timestamp tests are present in the repository. The owner accepted the M0 technical baseline on 2026-11-09, and an active `main` ruleset is recorded in the evidence below. Previous completion marks lacked complete evidence and have been cleared. CI and independent review for the subsequent hash-verification correction remain pending.

The [M0 evidence record](m0-evidence.md) links historical passing Ubuntu/macOS CI, explains its seed-package hash-verification gap, and records owner acceptance and ruleset 26885025. The correction requires its own immutable revision, successful CI, and independent review; M0 remains current and its gates remain open.

## M1 — Point-in-time market data
- [ ] Security master with delisting/history.
- [ ] Licensed OHLCV, corporate actions, data provenance and replay fixtures.
- [ ] Source availability is tested against decision timestamps.
- [ ] Unknown availability is quarantined; revision selection, security mappings, and universe joins pass independent temporal fixtures.
- [ ] Reproducible dataset snapshots, null/quality reporting.

## M2 — Backtester and accounting
- [ ] Reference ledger scenarios pass.
- [ ] Costs, partial fills, sessions, splits, and dividends tested.
- [ ] Future-data trap tests fail correctly.
- [ ] Runs reproducible by configuration and dataset revision.

## M3 — Strategy and statistical evaluation
- [ ] Simple momentum/reversion baselines, no invented P&L.
- [ ] Benchmark, chronological validation, holdout controls.
- [ ] Target units, replacement/expiry semantics, allocation, and sizing reference fixtures pass.
- [ ] Experiment/holdout protocol enforces registration, consumption before access, failure records, and selection counts.
- [ ] Complete environment manifests and derived/model training lineage are validated and replayed.
- [ ] Store all failed and successful experiments.
- [ ] Quantify uncertainty and trading cost sensitivity.

## M4 — AI research assistance
- [ ] Bounded proposal/implementation/reviewer workflow.
- [ ] No credential, deployment, or trading permissions.
- [ ] Research outputs have reproducible experiment IDs.
- [ ] Future-trained or unproven artifacts cannot produce historically eligible forecasts.

## M5 — Macro and event intelligence
- [ ] Release/consensus/revision timestamps and provenance verified.
- [ ] External features evaluated against technical-only baselines.
- [ ] Contradictory sources and missing information flagged.
- [ ] Recursive derived-feature availability and revision fixtures pass.

## M6 — SEC and public disclosures
- [ ] Form 4 and 13F parsing, amendment chains, lag-aware features.
- [ ] Political disclosures only after permitted-use review.
- [ ] Source links and uncertainty are visible.

## M7 — Paper trading
- [ ] Broker adapter isolated from research code.
- [ ] Idempotent order state and account reconciliation.
- [ ] Independent veto, emergency stop, failure drills.
- [ ] Actual ingestion/processing gates are enforced; historical-only eligibility cannot authorize operational input use.
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
