# Architecture

**Status:** design baseline with implemented `core.time` and `data` primitives
described below. The research, backtest, strategies, intelligence, portfolio, and
execution packages contain only docstrings reserving future module boundaries.
Review architectural changes through ADRs. M1 is the active milestone; its
acceptance gates remain open in the [roadmap](roadmap.md#m1--point-in-time-market-data).

## Mission
Long-lived, research-first U.S. equities platform for swing strategies and eventually paper/live execution. The platform is a **modular Python monolith** with narrow contracts, not a distributed system.

## Module ownership
- `core`: aware timestamps, identifiers, immutable domain contracts.
- `data`: ingestion, security master, corporate actions, point-in-time sources, lineage.
- `research`: feature computation, experiment metadata, validation, immutable results.
- `backtest`: deterministic event scheduling, fill simulation, accounting, costs.
- `strategies`: pure strategy functions from available observations to desired exposures.
- `intelligence`: macro, company events, SEC filings, later licensed alternative data.
- `portfolio`: account constraints, net exposures, candidate allocations, deterministic risk vetoes.
- `execution`: future paper/live adapters, order idempotency, reconciliation, safety stop.

## Dependency direction
- `core` imports no platform modules.
- `data` and `intelligence` depend on `core`, not on trading execution.
- `strategies` depend on stable domain contracts, not broker SDKs, databases, or web calls.
- `research` and `backtest` compose data, strategies, and domain contracts.
- `portfolio` consumes targets and known account state; never trusts a model's self-reported limits.
- `execution` accepts only pre-vetted orders. Research agents have no order permissions.
- Avoid cycles. An adapter may translate external records into core contracts; core never imports adapters.

## Data and replay
Store immutable raw snapshots separately from normalized curated datasets. Preserve source, revision/version, licensing, and temporal provenance. For historically valid simulation distinguish *first usable publication/source availability* from when the platform backfilled the record. Decisions must have a timestamp. Timezone-aware datetimes are mandatory.

`data.raw_archive` implements a local exact-byte payload store keyed by lowercase
SHA-256, with verification on put/get and atomic publication without replacement.
Version helpers use `ObservationVersion.content_sha256`; consumers select eligible
metadata before fetching, and missing/corrupt selected content fails without
fallback. Payloads persist on a trusted local POSIX filesystem with no crash
durability or provenance authentication. See
[ADR 0009](decisions/0009-local-raw-payload-archive.md).

Planned analytical storage: Parquet + DuckDB; neither is implemented or declared as
a runtime dependency. The implemented storage boundary is the local raw archive
above. Operational PostgreSQL is deferred until there is a real need for persistent
order state. An experiment must pin code revision, configuration, source snapshot
identifiers, seeds, and a complete [execution environment](environment.md). A code
revision or seed alone is insufficient for replay.

Data adapters distinguish quarantined raw records from validated availability. Historical replay uses proven public/provider availability; operational consumers additionally require actual ingestion and completed processing. Derived features must validate every input and model artifact against the decision cutoff. See [data contracts](data-contracts.md) for mode, revision, and lineage rules.

`data.admission` implements only the in-memory raw availability boundary: frozen
source claims produce accepted UTC timestamps or a quarantine result retaining
the raw envelope and field-specific reasons. Evidence references are adapter
assertions, not authenticated proof. See
[ADR 0006](decisions/0006-raw-availability-admission.md).

`data.receipts` binds the raw envelope, exact source URI/license ID and payload
digest to a frozen admission receipt. `LocalRawArchive` publishes payload first,
receipt last under a separate receipt digest, and verifies both on reopen. The
strict versioned codec preserves raw precision, text, timezone key/offset/fold,
and recomputes the named admission policy. This persists accepted and quarantined
assertions under ADR 0009's filesystem/failure assumptions; it does not create
validated observation versions or authenticate evidence. Provider ingestion,
operational processing, provider-backed catalog acceptance and dataset snapshots remain
unimplemented. See [ADR 0010](decisions/0010-persisted-raw-admission-receipts.md).

`data.receipt_sets` inventories an explicit sorted collection of receipt digests
and derives immutable admission/null/precision/status/reason counts. The archive
publishes a canonical versioned manifest/report object only after verifying all
receipts and payloads, then reopens every dependency and recomputes counts on load.
This counts raw assertions, without source coverage, revision selection, validated
promotion or an evaluable dataset snapshot. Empty collections explicitly report
zero counts. Existing publication/failure assumptions apply; see
[ADR 0011](decisions/0011-raw-receipt-set-quality-report.md).

`data.observation_records` persists explicit `ObservationVersion` assertions linked
to an existing accepted admission receipt. The archive verifies receipt/payload
dependencies and all shared identity, provenance and UTC instants before publishing
metadata last, then repeats those checks on reopen. The supplied version is never
derived from an accepted receipt alone. Canonical metadata timestamps use UTC while
raw receipts retain original representations. This adds individual metadata
retention, without source authentication, validated promotion
or a dataset snapshot. See
[ADR 0012](decisions/0012-receipt-linked-observation-records.md).

`data.catalog_inventories` persists explicit sorted observation-record membership.
It reopens every selected metadata/receipt/payload dependency and validates the
combined versions through existing catalog identity/rank/availability rules.
Frozen results retain record and receipt provenance and reconstruct a fresh
historical `VersionCatalog`. The canonical manifest is published last with existing
archive failure limits. It supplies no discovery, provider authenticity, coverage,
decision/query scope or evaluable dataset snapshot. See
[ADR 0013](decisions/0013-version-catalog-inventories.md).

`data.listings` adds an in-memory source-specific historical listing catalog.
Complete replacement histories bind stable security IDs to effective-dated
issuer/symbol/venue/currency intervals, including ended/delisted intervals. Queries
select the historically eligible metadata revision before filtering effective
time and retain selected provenance even when no interval matches. This is not
a complete security master or coverage guarantee;
see [ADR 0007](decisions/0007-historical-security-listings.md).

`data.listing_records` retains one explicit complete listing history against an
existing observation-record digest. The supplied full version must match through
the public metadata normalization boundary; interval text and tuple order remain
exact. Reopen verifies metadata/receipt/payload dependencies and reconstructs the
existing `ListingHistory` invariants. This preserves assertions and query
provenance, without proving source parsing, completeness or identity. Individual
listing records supply no global catalog index. See
[ADR 0014](decisions/0014-persisted-listing-history-records.md).

`data.universes` adds source-specific complete replacement membership histories
per stable security/universe. Historical membership queries retain both asserted
members and selected negative provenance. The listing join independently selects
membership and listing revisions at the same effective/decision times, retains
delisted members, and reports unresolved mappings explicitly. It establishes no
provider coverage or universe completeness; see
[ADR 0008](decisions/0008-point-in-time-universe-membership.md).

`data.membership_records` retains one explicit per-security/source/universe history
against matching observation metadata. Full supplied-version correspondence uses
the public metadata normalization boundary; ordered intervals and the complete
universe-ID suffix remain exact. Reopen verifies metadata, accepted receipt and
payload before reconstructing the current membership contract. Reopened histories
join independently selected listing histories without dropping delisted or
unresolved members. This adds no source authentication, universe completeness or
provider-backed acceptance. See
[ADR 0015](decisions/0015-persisted-membership-history-records.md).

`data.universe_listing_replays` pins explicit sorted listing/member record sets
and exact historical universe/source/venue/E/D scope. It reopens every dependency,
validates both whole catalogs before filtering, computes the existing stable-ID
join and requires exact canonical report equality. Selected history digests and
original tuple indices retain negative as well as positive context; unresolved
members remain explicit. The result is computed only, not caller-supplied. This
adds one consumer assertion artifact without source authentication, code/config/
environment collection or an evaluable dataset snapshot. See
[ADR 0016](decisions/0016-historical-universe-listing-replay.md).

Research registration and holdout consumption follow the [research protocol](research-protocol.md). These remain design contracts until M3 implements their persistent enforcement. Target exposures follow the [strategy contract](strategy-contract.md); portfolio conversion and accounting remain unimplemented.

## Execution boundary
Research, paper, and eventual live modes share strategy logic and risk policy contracts but **do not share credentials, mutable account state, or unapproved deployment paths**. Live mode does not exist in the scaffold. A future live implementation needs explicit owner authorization, external reconciliation, independent kill switch, and negative-path tests.

## Design exclusions in this scaffold
No broker calls; no order router; no strategy profitability claims; no LLM jobs; no satellite processing; no artificial enterprise service boundaries. New subsystems require a measured reason.
