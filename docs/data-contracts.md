# Data contracts (design draft)

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
reference, or persist quarantine. Each amendment needs its own evidence; no
earlier version's references are inherited. Source URI, license, content checksum,
revision rank, and retraction validation remain on `ObservationVersion` and its
adapter. Accepted timestamps alone do not establish a validated observation or
completed processing. See [ADR 0006](decisions/0006-raw-availability-admission.md).

### Eligibility by mode
- **Historical source replay:** `first_usable_at = max(published_at, source_available_at)` by UTC instant; the property returns UTC. `is_usable_at(T)` accepts equality and ignores backfill ingestion time. This reconstructs information accessible through the selected historical source, not information our platform actually observed. All comparisons normalize to UTC, including DST folds.
- **Operational observation:** `is_available_to_platform_at(T, processed_at=...)` additionally requires ingestion and completed local validation/processing no later than T. `processed_at` must be proven for this version and cannot precede ingestion. Missing processing evidence denies eligibility. Paper consumers must use this gate upstream of the shared strategy logic. No paper/live adapter exists yet.
- Both gates are necessary timestamp checks only. Data quality, as-of version selection, derived lineage, stale-input policy, and execution authorization are separate requirements. Timestamp equality does not authorize filling at the same bar's close: the scheduler must establish decision and fill ordering before M2 research use.

For each security/source/observation key, select the latest version eligible at the decision cutoff, never the latest version in today's database. Keep revisions immutable. Define a source-specific revision order and explicit tie-breaker; ambiguous duplicates, contradictory ordering, and unsupported retractions fail validation rather than selecting arbitrarily. Identifier mappings and universe membership must use their own effective dates and historically eligible versions. M1 must exercise revisions and temporal joins with independent fixtures.

`data.versions` implements only the in-memory historical selection rule for validated metadata. Its source-assigned integer revision ranks, uniqueness checks, and tie-break rule are specified in [ADR 0005](decisions/0005-observation-revision-selection.md). `data.admission` adds in-memory raw admission/quarantine results, `data.listings` adds effective-dated listing lookup, and `data.universes` adds membership and its stable-ID listing join. `data.raw_archive` persists exact payload bytes as described below. Durable quarantine, source-order proof, provider ingestion, coverage/completeness and metadata persistence remain M1 work. Raw envelopes and admission results cannot enter the catalogs directly; a selected metadata version alone is not an evaluable dataset.

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
arguments raise `ValueError`; `RawArchiveError` subclasses distinguish supplied
digest mismatch, missing payload, corrupt payload and filesystem I/O failure.
`ArchiveIOError` can follow successful publication if staging cleanup fails;
retry verifies the complete existing object but does not clear stale staging files.

The caller controls the trusted root, permissions and capacity, and must exclude
hostile/concurrent mutation except cooperating no-replace publishers. This supports
local POSIX filesystem semantics only. No `fsync`, crash durability, recovery,
garbage collection, source/tenant isolation, metadata/quarantine persistence or
dataset manifests are provided. Read-only file permissions are not tamperproofing.
See [ADR 0009](decisions/0009-local-raw-payload-archive.md) for the storage rationale,
failure semantics and acceptance limits.

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
