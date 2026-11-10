# Data contracts

The named temporal/catalog/archive/receipt APIs below are implemented. Market
bars, corporate actions, filings, alternative data, derived lineage and evaluable
dataset snapshots remain design requirements. See the
[active M1 scope](roadmap.md#m1--point-in-time-market-data)
and [testing evidence](testing-strategy.md#scope-of-current-scaffold); API presence
does not mean a milestone gate has been accepted.

## Core identifiers
Use stable security IDs with issuer/security mappings and effective dates. Tickers are display symbols, not permanent identities. Exchanges, currencies, delistings, and corporate actions need explicit definitions.

`data.listings` implements an in-memory historical listing identity slice.
`ListingHistory` binds a complete replacement tuple of immutable `ListingInterval`
records to an `ObservationVersion` keyed by `(security_id, source_id,
observation_id="listing-history")`, covering all venues for that security/source.
Intervals retain exact issuer ID, symbol, venue and currency, with real aware UTC
half-open effective boundaries. Every ended interval requires a nonblank
source-defined end reason; open intervals prohibit an end reason. Same-venue
overlaps within a history fail, while adjacency and multiple venues are valid.

`ListingCatalog.listing_at` and `resolve_symbol_at` require both `effective_at`
and `decision_at`, with effective time no later than decision time. They select
each latest eligible complete history through `VersionCatalog` before examining
its intervals, so an omitted interval never falls back to an older revision.
Symbol resolution uses exact source/venue/symbol and raises on multiple matching
securities. Query results retain selected metadata even for absent matches,
the matched interval/version when present, and UTC query timestamps. Neither no
eligible history nor an absent interval proves real-world absence or source
completeness. DST gaps reject; valid folds compare by UTC instant. See
[ADR 0007](decisions/0007-historical-security-listings.md) for the key scheme,
complete replacement assumption, end reasons, and provenance limitations.
Source identity proof, canonical payload hashing, and operational consumption
remain unimplemented.

`data.universes` adds immutable complete replacement `MembershipHistory` records
per `(security_id, source_id, universe_id)`. The exact observation ID is the fixed
prefix `"universe-membership-history:"` followed by the complete nonblank universe
ID, constructed by `membership_observation_id`. Histories bind validated versions
to UTC half-open `MembershipInterval` tuples; overlapping/duplicate intervals fail,
adjacency is valid, and only explicit tuple/list containers can assert an empty
replacement. Universe IDs and source IDs are exact, with no normalization.

`UniverseCatalog.members_at` requires effective time no later than decision time,
selects each latest eligible revision before filtering intervals, and returns
asserted stable member IDs with matched intervals and selected provenance for
positive and negative histories. Removing an interval never falls back to an older
revision. Empty replacements affect only their security/source/universe key,
not unmentioned securities. Missing eligibility and negative assertions remain
distinct; neither establishes source coverage or universe completeness.

`UniverseCatalog.listings_at` takes an explicit `ListingCatalog`, listing source
and venue, and joins each asserted stable member ID at the same E/D. Each source
independently applies its own publication/provider availability cutoff. The result
retains membership context and every per-member listing lookup, exposes matched
listings and explicit unresolved member IDs, and keeps negative mapping provenance.
A delisted member or a missing mapping is never silently discarded or rebound by
current ticker. Distinct stable members sharing a display symbol remain distinct;
explicit symbol resolution still raises on ambiguity through `ListingCatalog`.
Times reject DST gaps and distinguish valid folds. See
[ADR 0008](decisions/0008-point-in-time-universe-membership.md) for scope and limits.

## Time and provenance
For every external observation store:
- `event_at`: when the economic activity or underlying event occurred (if known).
- `published_at`: when this version of the content was first publicly released.
- `source_available_at`: when the selected provider actually made this version available.
- `ingested_at`: when our infrastructure fetched/recorded it.
- `source_id`, `source_uri`, `license_id`, `version_id`, and content checksum.
- An uncertainty/missing marker for timestamps that cannot be proven.

Raw ingestion records may retain null timestamps with a reason and source evidence; ingestion must not invent timestamps, substitute event time for release time, or silently parse a date into a midnight release. Unknown `event_at` is permitted because an event may be undated or announced in advance. Unknown or uncertain publication/provider availability makes a raw observation **ineligible**: quarantine it until evidence establishes exact availability. Approximate dates, estimated lags, and unproven vendor claims must not enter the validated contract. A future policy for proven conservative bounds requires an ADR and reference cases.

`core.time.InformationAvailability` is the validated timestamp envelope, not the raw ingestion record. `event_at` accepts `None`; publication, provider availability, and ingestion must be timezone-aware datetimes. Missing, unparsed, and naive required timestamps raise `ValueError`. Provenance evidence remains the adapter's responsibility: the type cannot authenticate timestamps or make an uncertain estimate proven.

`data.admission` provides an in-memory raw boundary before that validated envelope.
Immutable `RawTimestampClaim` records retain parsed datetime/date/`None`, original
source text, exact/unknown/approximate/unverified status, evidence reference, and
uncertainty reason. `RawAvailability` retains the observation key, version ID,
event time, both release claims, and ingestion time. Adapters preserve date-only
precision and never invent an instant from it; this module performs no parsing.
Original source text is optional: it is retained when supplied, but an exact
claim with a nonblank evidence reference may have `source_text=None`.
`admit_availability` returns `AcceptedAvailability` with UTC-normalized validated
times, or `QuarantinedAvailability` with the unchanged raw envelope and all
field-specific reasons. Required release claims must be exact, aware datetimes
with nonblank evidence references and no declared uncertainty. Missing values,
date-only/naive claims, missing evidence, uncertain status, or a nonblank
uncertainty reason quarantine; unknown event time is allowed. Naive event or
ingestion times also quarantine. All supplied datetimes must survive a UTC
roundtrip to the same civil time and offset; nonexistent local times in a DST
spring gap quarantine, while both valid fall folds remain distinct instants.
Invalid API types raise `ValueError`.

Admission checks the shape of an adapter's assertions; it does not authenticate
evidence, compare parsed values with source text, prove version ownership of a
reference, or itself persist quarantine. Each amendment needs its own evidence; no
earlier version's references are inherited. Source URI, license, content checksum,
revision rank, and retraction validation remain on `ObservationVersion` and its
adapter. Accepted timestamps alone do not establish a validated observation or
completed processing. See [ADR 0006](decisions/0006-raw-availability-admission.md).

### Eligibility by mode
- **Historical source replay:** `first_usable_at = max(published_at, source_available_at)` by UTC instant; the property returns UTC. `is_usable_at(T)` accepts equality and ignores backfill ingestion time. This reconstructs information accessible through the selected historical source, not information our platform actually observed. All comparisons normalize to UTC, including DST folds.
- **Operational observation:** `is_available_to_platform_at(T, processed_at=...)` additionally requires ingestion and completed local validation/processing no later than T. `processed_at` must be proven for this version and cannot precede ingestion. Missing processing evidence denies eligibility. Paper consumers must use this gate upstream of the shared strategy logic. No paper/live adapter exists yet.
- Both gates are necessary timestamp checks only. Data quality, as-of version selection, derived lineage, stale-input policy, and execution authorization are separate requirements. Timestamp equality does not authorize filling at the same bar's close: the scheduler must establish decision and fill ordering before M2 research use.

For each security/source/observation key, select the latest version eligible at the decision cutoff, never the latest version in today's database. Keep revisions immutable. Define a source-specific revision order and explicit tie-breaker; ambiguous duplicates, contradictory ordering, and unsupported retractions fail validation rather than selecting arbitrarily. Identifier mappings and universe membership must use their own effective dates and historically eligible versions. M1 must exercise revisions and temporal joins with independent fixtures.

`data.versions` implements the in-memory historical selection rule for validated metadata. Its source-assigned integer revision ranks, uniqueness checks, and tie-break rule are specified in [ADR 0005](decisions/0005-observation-revision-selection.md). `data.admission` adds in-memory raw admission/quarantine results, `data.listings` adds effective-dated listing lookup, and `data.universes` adds membership and its stable-ID listing join. `data.raw_archive` persists exact payload bytes and `data.receipts` adds raw admission/quarantine receipts as described below. `data.observation_records` adds individual receipt-linked metadata assertions; `data.catalog_inventories` retains explicit collections validated against the existing selector rules. Quarantine processing workflows, source-order proof, provider ingestion and coverage/completeness remain M1 work. Raw envelopes and admission results cannot enter the catalogs directly; a metadata inventory alone is not an evaluable dataset.

### Local raw payload archive

`LocalRawArchive(root: Path)` requires an existing absolute local directory with
no `..` or symlink components. `put(content_sha256, payload: bytes)` verifies
SHA-256 before writing; `get(content_sha256)` verifies the stored file before
returning its exact bytes. Keys are exact lowercase 64-character SHA-256 hex,
used as flat filenames. Text and mutable buffers reject; empty/binary bytes are
valid. No canonical serialization, decoding, or normalization occurs. Adapters
must hash the exact source representation they archive.

`put_version` and `get_version` require `ObservationVersion` and use exactly its
`content_sha256`. Consumers select eligible metadata first; a failed selected
payload lookup raises, without falling back to a readable older revision. The
archive has no temporal selection logic. Ingestion, availability, processing,
revision rank, source/license, identity and evidence claims are neither inferred
nor authenticated by storing bytes.

New content is staged, closed and reverified before atomic no-replace hard-link
publication. A repeated put verifies existing bytes and their equality; it never
replaces or repairs corrupt content. Symlink/nonregular objects reject. Invalid
argument types/values raise `ValueError`; a missing, non-directory, symlinked or
inaccessible archive root raises `ArchiveIOError`. `RawArchiveError` subclasses
distinguish supplied digest mismatch, missing payload, corrupt payload and
filesystem I/O failure.
`ArchiveIOError` can follow successful publication if staging cleanup fails;
retry verifies the complete existing object but does not clear stale staging files.

The caller controls the trusted root, permissions and capacity, and must exclude
hostile/concurrent mutation except cooperating no-replace publishers. This supports
local POSIX filesystem semantics only. The payload API provides no `fsync`, crash
durability, recovery, garbage collection, source/tenant isolation or dataset
manifest. Separate receipt, metadata and inventory extensions follow below.
Read-only file permissions are not tamperproofing.
See [ADR 0009](decisions/0009-local-raw-payload-archive.md) for the storage rationale,
failure semantics and acceptance limits.

### Raw admission and quarantine receipts

`data.receipts.AdmissionReceipt(raw, source_uri, license_id, content_sha256)` is
frozen. It retains exact nonblank source/license strings and derives the current
`admit_availability` result and `raw-availability-v1` policy ID. A receipt is not
an `ObservationVersion` and cannot enter the existing catalogs directly.

`encode_receipt` produces deterministic schema-version-1 ASCII JSON, whose complete
shape and exact bytes are pinned by `tests/fixtures/admission-receipt-v1.json`.
`decode_receipt` rejects duplicate/unknown/missing fields, wrong types, unsupported
schema/policy, noncanonical bytes, or a stored outcome/UTC fields/quarantine reasons
that differ from recomputed admission. Original claim text, source identifiers,
evidence and uncertainty strings are preserved exactly, including whitespace.
Date, datetime and `None` remain distinct. Datetimes retain civil fields and fold,
with explicit naive/UTC/fixed-offset/keyed-ZoneInfo representations. Fixed offsets
retain microseconds and name; ZoneInfo retains key, observed offset and name and
must reproduce them on load. No ISO offset is silently reinterpreted; unavailable
or changed zone rules fail. Both nonexistent DST gap folds remain quarantined;
valid folds retain distinct UTC instants. Unsupported datetime/date subclasses
and tzinfo implementations reject at this new codec boundary; existing in-memory
constructors remain unchanged. The codec does not pin a full timezone database.

`LocalRawArchive.put_receipt(receipt, payload) -> str` encodes first, verifies/stores
the exact payload, then publishes the receipt under its separate receipt SHA-256.
Both use the existing no-replace protocol. Identical payloads may have distinct
receipts for different provenance/versions. The caller retains the receipt digest;
there is no index or discovery API. `get_receipt(digest)` verifies and strictly
reopens the receipt, recomputes admission, then verifies its referenced payload.
Missing/corrupt selected objects fail without fallback. `ReceiptMissingError` and
`ReceiptCorruptError` inherit `RawArchiveError`; referenced payload and filesystem
failures retain their existing error types. `ReceiptFormatError` is the standalone
codec's `ValueError` subtype.

Pre-publication failure exposes no new complete receipt; verified payload bytes
may remain unreferenced. As in ADR 0009, cleanup or directory-close failure after
linking can raise with a complete receipt already visible; retry verifies existing
content. No crash durability or multi-object crash transaction is promised. Receipt
retention authenticates neither evidence nor source/license claims, does not grant
historical catalog eligibility, and does not record completed processing. Provider
ingestion, quarantine queues/reprocessing, provider-backed catalog acceptance,
coverage reports and reproducible dataset snapshots remain unimplemented. See
[ADR 0010](decisions/0010-persisted-raw-admission-receipts.md).

### Explicit raw receipt sets and quality counts

`data.receipt_sets.ReceiptSetManifest` pins distinct lowercase receipt digests in
sorted immutable order. `build_receipt_set(archive, receipt_sha256s)` and
`LocalRawArchive.put_receipt_set(receipt_sha256s)` take explicit built-in tuple/list
collections; invalid entries/containers and duplicates reject before access.
Every member loads through `get_receipt`, including payload verification. Same
payloads, keys or versions do not merge distinct receipt identities. An empty
collection is valid and includes neither unmentioned receipts nor inferred data.

The frozen `RawReceiptSet` bundles its manifest and `ReceiptSetQualityReport`.
Counts use selected receipt identities: accepted plus quarantined equals receipt
count. Unknown event count is `event_at is None`, which admission permits. Both
release fields have all receipts as denominator, separate null counts for parsed
value/source text/evidence reference/uncertainty reason, date-only counts excluding
datetimes, and exact/unknown/approximate/unverified counts that partition that
denominator. Null means `None`; blank text is retained distinctly. Optional source
text can be null on acceptance and exact claims normally have no uncertainty
reason: these are descriptive raw counts, not automatic defects. Null, date and
status dimensions can overlap. Exact `(field, reason)` groups count quarantined
receipts with that pair, once per receipt, including event/ingestion issues.
Multiple reasons can make their sum exceed quarantined count; groups sort by
field/reason and zero-occurrence groups are omitted. Empty collections yield
zero counts in both release records and no quarantine groups. No percentages,
coverage or completeness claims are inferred.

`encode_receipt_set`/`decode_receipt_set` define schema-1 canonical ASCII JSON,
including `raw-availability-v1` and `raw-receipt-quality-v1` policy IDs and the full
manifest/report together. Archive put verifies all dependencies before publishing
this one object last, returning its SHA-256. Get verifies object bytes, reloads
all receipts/payloads, recomputes report and requires exact canonical bytes.
Rehashed summary tampering, unknown schema/policies, duplicate JSON keys,
noncanonical JSON/order and invalid membership reject. A standalone encoder does
not verify dependencies. The caller retains the set digest; no discovery exists.

`ReceiptSetFormatError` is a codec `ValueError`; `ReceiptSetMissingError` and
`ReceiptSetCorruptError` inherit `RawArchiveError`. Dependency receipt/payload and
filesystem errors propagate unchanged. Any member failure prevents success;
there is no fallback or partial result. ADR 0009's pre/post-link failure distinction,
retry semantics, trusted POSIX filesystem and no-crash-durability limits apply.
This is an inventory of raw assertions, without decision cutoff, revision selection,
validated metadata promotion, processing evidence, transform/code/environment pins,
source authentication or evaluable dataset snapshot. See
[ADR 0011](decisions/0011-raw-receipt-set-quality-report.md).

### Receipt-linked observation-version records

`data.observation_records.ReceiptLinkedVersion(version, receipt_sha256)` retains
an explicit supplied `ObservationVersion` and an existing raw receipt reference.
Direct construction/encoding validates shape only. A version is never inferred
from an accepted receipt. `build_observation_record(archive, version, receipt_sha256)`
reopens the exact receipt and its payload, requires accepted admission, and matches
key, version ID, exact source URI/license text, payload digest and all four
availability fields. Unknown event time matches only unknown event time. Source
revision rank remains an explicit caller assertion; linkage authenticates neither
that rank nor source, identity, license or timestamp evidence.

This boundary requires standard datetimes with UTC, standard fixed offsets or
reopenable keyed `ZoneInfo` rules. Civil times must survive a UTC roundtrip before
normalization; gaps reject and valid folds retain distinct instants. Zone keys must
reproduce offset/name. Out-of-range UTC conversion rejects as `ValueError`.
Equivalent representations of one real instant are accepted. The returned version
uses UTC with `fold=0`, while the raw receipt retains original representations.
Ranks must be standard nonnegative `int` values: bool, float and integer subclasses
reject at this boundary, without changing the existing in-memory constructors.

`encode_observation_record` produces schema-1 canonical ASCII JSON with the full
version fields, receipt digest and `receipt-linked-observation-v1` policy ID.
Timestamps use UTC with six fractional digits and `Z`; only `event_at` may be null.
`decode_observation_record(payload, archive)` rejects duplicate/unknown/missing
fields, unsupported schemas/policies/types, alternate timestamp spellings and
noncanonical bytes, then repeats all dependency/linkage checks. Rehashed edits
cannot conceal mismatches. The literal schema fixture is
`tests/fixtures/observation-record-v1.json`.

`LocalRawArchive.put_observation_record(version, receipt_sha256) -> str` verifies
existing dependencies before publishing one metadata object last, returning its
separate digest. `get_observation_record(digest)` verifies the object and every
dependency before returning. Neither creates receipts/payloads nor records
processing completion. Existing `put_version/get_version` still address payloads.
`ObservationRecordFormatError` is a standalone codec `ValueError`;
`ObservationRecordMissingError`/`ObservationRecordCorruptError` are archive-load
errors under `RawArchiveError`. Referenced receipt/payload/filesystem failures
propagate unchanged. Put retains existing base publication error types.

The caller retains record digests; the individual-record API provides no index,
discovery or dataset snapshot. Explicit catalog inventories are the separate
extension below. ADR 0009's trusted POSIX, no-replace and pre/post-link
failure/retry limits apply, including no crash durability or cleanup recovery.
See [ADR 0012](decisions/0012-receipt-linked-observation-records.md).

### Explicit version-catalog inventories

`data.catalog_inventories.VersionCatalogManifest(observation_record_sha256s)`
accepts built-in tuples/lists and snapshots distinct lowercase record digests into
sorted immutable order. All entries and duplicates validate before dependency
reads. `build_version_catalog_inventory(archive, observation_record_sha256s)`
requires a `LocalRawArchive` even for empty membership, reopens every selected
record through `get_observation_record`, and returns a frozen
`VersionCatalogInventory(manifest, records)`. Records must be an immutable tuple
in manifest digest order and reproduce every manifest digest exactly.

All selected versions jointly satisfy `VersionCatalog` rules: duplicate version
IDs/ranks within one key and revision availability contradicting rank reject.
Identical payloads/receipts never merge distinct metadata assertions. Independent
keys may reuse IDs/ranks. `inventory.to_catalog()` reconstructs a fresh selector
using existing inclusive historical release cutoffs and rank tie-breaking;
backfill ingestion does not shift those cutoffs. Original record/receipt provenance
remains on the inventory. Neither construction nor selection authenticates it.

`encode_version_catalog_inventory` produces schema-1 canonical ASCII JSON containing
only the manifest, schema and `observation-version-catalog-v1` policy ID. Record
bodies remain dependencies. The encoder checks no archive.
`decode_version_catalog_inventory(payload, archive)` rejects unsupported types,
schemas/policies, duplicate/unknown/missing fields, unsorted/duplicate membership
and noncanonical bytes before dependency reads where possible. It then reloads
every dependency, revalidates catalog rules and requires exact canonical bytes.
The literal fixture is `tests/fixtures/version-catalog-inventory-v1.json`.

`LocalRawArchive.put_version_catalog_inventory(digests) -> str` verifies all
dependencies before publishing the manifest last and creates no observation,
receipt or payload. `get_version_catalog_inventory(digest)` verifies the inventory
and its complete selected dependency graph. Standalone malformed/inconsistent
metadata raises `VersionCatalogInventoryFormatError`, a `ValueError`; inventory
loads distinguish `VersionCatalogInventoryMissingError` and
`VersionCatalogInventoryCorruptError` under `RawArchiveError`. Dependency errors
propagate unchanged; no partial result, fallback, removal or repair is returned.
Existing trusted-POSIX and pre/post-publication failure/retry limits apply.

Callers retain inventory digests; there is no global index/discovery. An explicit
empty inventory includes no unmentioned objects and proves no source absence or
coverage. The manifest carries no decision/effective query scope, code/config/
environment pins, transform lineage, processing evidence or completeness report.
It is not an evaluable dataset snapshot. See
[ADR 0013](decisions/0013-version-catalog-inventories.md).

### Persisted listing-history assertions

`data.listing_records.ListingHistoryRecord(history, observation_record)` requires
an explicit `ListingHistory` and `ReceiptLinkedVersion`. The supplied history's
full version is normalized through the public ADR 0012 metadata boundary and its
canonical observation-record bytes must match the referenced record, including
rank, key, provenance and all timestamps. This does not discard a different
supplied version or infer a version from admission. Returned records retain both
the normalized history and exact metadata/receipt provenance.

Intervals are revalidated through existing public listing constructors. Exact
issuer/symbol/venue/currency/end-reason text and the caller's interval tuple order
are preserved. The fixed `listing-history` key, all-venue complete replacement,
UTC half-open intervals, no overlaps per security/venue and explicit empty
replacement semantics remain unchanged. The interval constructor has already
normalized original zones to UTC; persistence does not recover those original
representations. At this narrower codec boundary, endpoints must be standard UTC
datetimes and normalize `fold=0`. Their canonical strings use six fractional
digits and `Z`. Existing in-memory constructors are unchanged.

`build_listing_history_record(archive, history, observation_record_sha256)`
verifies the existing observation record, accepted receipt and exact payload
before version correspondence checks. `encode_listing_history_record` writes
schema-1 canonical ASCII JSON with `receipt-linked-listing-history-v1`, the pinned
observation-record digest and ordered interval fields; the version remains in its
content-addressed dependency. Direct construction/encoding validates assertions,
not dependency existence or source truth.
`decode_listing_history_record(payload, archive)` strictly parses schemas/policies,
field sets, duplicate keys, types, canonical UTC spellings and bytes, then verifies
dependencies and reconstructs the complete history. The literal reference chain
is `tests/fixtures/listing-receipt-v1.json`, `listing-observation-record-v1.json`
and `listing-history-record-v1.json`.

`LocalRawArchive.put_listing_history_record(history, observation_record_sha256)`
publishes one listing assertion last and returns its digest, creating no metadata,
receipt or payload. `get_listing_history_record(digest)` verifies the exact listing
record and every dependency. `ListingHistoryRecordFormatError` is the standalone
codec `ValueError`; archive loads distinguish `ListingHistoryRecordMissingError`
and `ListingHistoryRecordCorruptError` under `RawArchiveError`. Dependency errors
propagate unchanged. Existing no-replace, pre/post-link failure and retry limits
apply without crash durability, recovery, fallback or repair.

Valid changed intervals/order or a reference to another fully valid listing
version create new assertions. Their hashes do not prove parsing from raw bytes,
complete source scope or truthful identity. Conflicting histories may reference
one version; a future collection boundary must reject conflicting identities.
Callers retain listing digests. No listing inventory, membership serialization,
coverage report, provider acceptance or evaluable dataset snapshot is added. See
[ADR 0014](decisions/0014-persisted-listing-history-records.md).

### Derived features and model artifacts
Every derived output must pin input snapshot/version IDs, transform code and parameters, artifact ID/checksum (if any), and its actual computation/completion timestamp. Artifacts must record their release/first-usable time, training-data cutoff and snapshot IDs, fitted preprocessing/calibration, and tuning/selection lineage. Preprocessing and model fitting must use only the permitted training partition. Unknown training provenance makes an artifact ineligible for historical predictive evaluation; it may still produce explicitly labeled exploratory proposals.

In historical replay, a deterministic recomputation may occur today, but all its input versions and any fitted artifact must have been usable by the simulated decision. Derived historical availability is no earlier than the maximum of those dependencies' eligible availability times. A model trained or released after T cannot generate a supposedly available forecast at T. Choosing a transform using later outcomes is strategy selection and is subject to the research protocol, even if the underlying inputs are old.

For operational use, the derived output must also have actually completed validation/processing and reached its consumer by T; source timestamps cannot stand in for that completion. Source and artifact lineage is recursive, so an eligible final timestamp cannot conceal an ineligible dependency. The current timestamp primitive does not implement a feature/artifact lineage validator. M3/M4/M5 cannot claim these gates complete until their respective consumers enforce them and adversarial future-artifact cases pass.

## Market bars
A bar needs a stable security ID, trading venue, interval start/end, currency, raw OHLCV, vendor, adjusted/raw convention, source revision, and availability metadata. Define exact bar-completion and next-execution rules before research use.

## Corporate actions
Preserve split ratios, cash/stock distributions, effective/ex dates, announcements, and observation versions. Never double-count adjustments in both bar data and position accounting.

## Filings and disclosures
Preserve filing identity, amendment chain, submitted/public timestamp, covered reporting period, beneficial-owner/manager ID, security mapping, and reported value-range/precision. A 13F quarter-end holding is not a contemporaneous trade. Politician filings often disclose ranges, not exact amounts; do not fabricate sizes.

## Alternative data
Enforce license rights, geographic/store mapping, observation quality, coverage gaps, time-of-day/seasonality metadata, and estimated cost. Satellite data must record acquisition and delivery timestamps separately.

## Dataset snapshots
Immutable manifest: source versions, transforms and checksums, code revision, as-of cutoff, coverage report, and anomaly counts. Pin the environment manifest/hash and applicable transform/artifact lineage. Store repository-local raw datasets in `/data/`, generated artifacts in `/artifacts/`, and exported results in `/outputs/`; these root directories are ignored, while `src/quant_test/data/` is source code. Invalid/unknown values should produce explicit flags, not automatically filled zeroes.

See [environment requirements](environment.md), [research protocol](research-protocol.md), and [ADR 0002](decisions/0002-information-eligibility.md).
