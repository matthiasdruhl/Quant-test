# ADR 0005: In-memory historical observation revision selection

- **Status:** Proposed for M1 review
- **Date:** 2026-11-09

**Subsequent extensions:** this ADR's exclusions describe the revision-selector
slice. Effective-dated [listings](0007-historical-security-listings.md) and
[membership joins](0008-point-in-time-universe-membership.md), plus
[raw storage](0009-local-raw-payload-archive.md) and
[receipt retention](0010-persisted-raw-admission-receipts.md), are now implemented
separately. [ADR 0012](0012-receipt-linked-observation-records.md) retains individual
supplied version assertions with verified raw receipt linkage, without creating a
catalog inventory. Provider ingestion, validated catalog persistence and dataset snapshots
remain open; see the [current contracts](../data-contracts.md).

## Context
An observation can be revised after its first release. Choosing the latest version in a present-day dataset leaks future revisions into an earlier decision. Publication and provider availability can differ, and today's ingestion time must not move a proven historical release. Ambiguous provider ordering must fail rather than depend on input iteration order.

## Decision
`data.versions` introduces an immutable metadata record keyed by stable `security_id`, `source_id`, and `observation_id`. The source adapter must document and assign a nonnegative integer `revision_rank` for each version. The catalog requires unique version IDs and ranks within a key, and nondecreasing historical first-usable times as rank increases. Equal usable instants are resolved by the explicit rank. Duplicate/conflicting ranks, reversed availability order, and flagged retractions are rejected. The selector returns the highest rank whose validated public and provider availability is no later than the decision instant, or `None` when no version is eligible. Input ordering and backfill ingestion time do not affect selection.

Each record requires a source URI, license ID, version ID, and lowercase SHA-256 content digest. It holds no observation payload. `InformationAvailability` provides the existing UTC timestamp gate; this API adds no operational eligibility claim. A raw record with missing, approximate, or unproven release time must remain outside this catalog. An adapter still has to preserve the raw uncertainty reason and evidence, authenticate source timestamps, verify the digest against stored bytes, and establish that its rank matches provider revision semantics. The catalog cannot do those jobs.

## Scope and consequences
This is an in-memory selection primitive, not a data lake, security master, market-bar convention, or ingestion pipeline. It does not implement quarantine storage, provider revision extraction, retraction policy, effective-dated mappings, universe membership, snapshots, or operational processing gates. No runtime dependency or accounting convention is added. M1 boxes stay open until those integrations, independent review, and CI evidence exist.

The contract tests use hand-specified release boundaries, reverse input order, identity partitioning, equal-time ties, invalid metadata, unknown release values, offset/DST instants, and contradiction failures. Adapters will need source-specific fixtures before their outputs can be trusted by research or backtesting.
