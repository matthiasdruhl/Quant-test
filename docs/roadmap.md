# Incremental roadmap and definition of done

Estimated timing is optional; **gates are evidence-based**. Do not treat checkboxes as completed until demonstrated in CI and independent owner/reviewer review. Every completed gate must link to its immutable source revision, CI run (where executable), acceptance results, and review record in the PR or an evidence record. For a manual gate, record the owner, date, and verifiable outcome. Missing evidence leaves the box unchecked. Agents may report local checks but cannot invent CI/review approval or promote a milestone.

## M0 — Governance and skeleton (complete)
- [x] Versioned architecture, source boundaries, temporal and trading contracts accepted in review. [Evidence](m0-evidence.md#m0-gate-evidence).
- [x] Minimal installable Python package and hash-locked CI configuration verified. [Evidence](m0-evidence.md#hash-verification-correction-verified-revision-and-ci).
- [x] Time-availability primitive and explicit unimplemented modules verified in CI/review. [Evidence](m0-evidence.md#m0-gate-evidence).
- [x] CI has actually run successfully on GitHub. [Evidence](m0-evidence.md#hash-verification-correction-verified-revision-and-ci).
- [x] Owner-approved repository protection/rulesets are active (where available). [Evidence](m0-evidence.md#repository-protections-active-ruleset).

The owner accepted the M0 technical baseline on 2026-11-09. The hash-verification correction merged at [6e6ce45d88a90524152da8c12a7c198ae7df224b](https://github.com/matthiasdruhl/Quant-test/commit/6e6ce45d88a90524152da8c12a7c198ae7df224b), with passing [post-merge Ubuntu/macOS CI 42694728391](https://github.com/matthiasdruhl/Quant-test/actions/runs/42694728391) that checked out that exact revision. Earlier [PR CI 42694437775](https://github.com/matthiasdruhl/Quant-test/actions/runs/42694437775) tested GitHub's synthetic merge, not the literal PR head. Independent correction reviews and the identical source tree shared by the correction head and merged `main` are recorded in the [M0 evidence record](m0-evidence.md#independent-review-record). The four technical gates above have evidence for completion; owner acceptance of the earlier baseline is not a claim of owner acceptance of the correction.

The [M0 evidence record](m0-evidence.md) preserves the historical CI hash-verification limitation and records its correction. Active `main` ruleset 26885025 was verified and accepted under the owner's delegated authority on 2026-11-09. The protection gate records approval of that active policy; it does not claim the owner personally configured it. All five M0 gates are complete on the linked evidence; M1 acceptance is separately scoped.

## M1 — Point-in-time market data
**Active milestone.** Implemented slices below are partial progress; all five
acceptance gates remain open.

The [proposed Databento Security Master source contract](sources/databento-security-master.md)
records a first listing-history candidate, its documentation evidence and the
rights, availability, identity and completeness questions blocking validated
ingestion. This is qualification work, not a selected provider or closed gate.

- [ ] Security master with delisting/history.
- [ ] Licensed OHLCV, corporate actions, data provenance and replay fixtures.
- [ ] Source availability is tested against decision timestamps.
- [ ] Unknown availability is quarantined; revision selection, security mappings, and universe joins pass independent temporal fixtures.
- [ ] Reproducible dataset snapshots, null/quality reporting.

The in-memory timestamp gate, revision catalog, raw availability
admission/quarantine result, historical listing catalog, and universe membership/
listing join are implemented with local deterministic reference
tests; see [ADR 0005](decisions/0005-observation-revision-selection.md) and
[ADR 0006](decisions/0006-raw-availability-admission.md), and
[ADR 0007](decisions/0007-historical-security-listings.md), and
[ADR 0008](decisions/0008-point-in-time-universe-membership.md). The listing slice covers
source-specific complete replacement histories, effective/decision time lookup,
and preserved delistings, not the complete security master. The membership slice
preserves asserted stable IDs, independent source revision selection, negative
provenance and explicit unresolved listing joins; it does not establish source
coverage or complete real-world universes. The local exact-byte raw payload
archive verifies checksums and publishes without replacement; see
[ADR 0009](decisions/0009-local-raw-payload-archive.md). Its payload API persists exact bytes
under trusted local POSIX filesystem assumptions and makes no crash durability
claim. Raw admission/quarantine receipts now retain exact payload provenance and
raw claims under a separate digest, with a strict versioned codec and recomputed
admission on reopen; see
[ADR 0010](decisions/0010-persisted-raw-admission-receipts.md). This adds raw receipt
retention, without a quarantine processing workflow or validated metadata catalog.
Explicit raw receipt sets now pin selected receipt digests and persist a canonical
manifest with recomputed admission/null/precision/status/reason counts; see
[ADR 0011](decisions/0011-raw-receipt-set-quality-report.md). These descriptive
counts include accepted and quarantined assertions and do not establish source
coverage, validated observation promotion, revision selection or dataset snapshots.
Individual receipt-linked observation records now persist explicitly supplied
metadata assertions and verify their exact accepted raw receipt/payload linkage
before publication and on reopen. They do not infer a version from admission or
authenticate source rank/provenance; evaluable snapshots remain unimplemented. See
[ADR 0012](decisions/0012-receipt-linked-observation-records.md).
Explicit immutable version-catalog inventories now retain selected observation
record digests, reverify the complete dependency graph and reconstruct historical
selection after validating combined identity/rank/availability rules. They carry
no query cutoff, coverage or source-authenticity guarantee and are not evaluable
dataset snapshots. See [ADR 0013](decisions/0013-version-catalog-inventories.md).
These primitives do not authenticate evidence or implement provider ingestion,
source revision/identity proof, coverage/completeness reporting, or dataset snapshots. All M1 gates remain open pending their complete acceptance
evidence, CI, and independent review.

Implementation verification as of 2026-11-09: [PR #10](https://github.com/matthiasdruhl/Quant-test/pull/10)
merged the receipt-set slice at
[`f9a49d8c8a8bca55bccb5c1a1a0678f31747d54c`](https://github.com/matthiasdruhl/Quant-test/commit/f9a49d8c8a8bca55bccb5c1a1a0678f31747d54c).
[Post-merge CI 42712502514](https://github.com/matthiasdruhl/Quant-test/actions/runs/42712502514)
checked out that exact revision on Ubuntu 24.04 and macOS 15; both jobs passed all
quality/build/hash checks and 393 tests. This verifies the implemented primitives
at that revision and does not supply the missing provider integration or complete
M1 acceptance evidence. The [documentation audit](documentation-audit.md) records
the separate local checks and review limitations.

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
