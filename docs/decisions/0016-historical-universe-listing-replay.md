# ADR 0016: Historical universe-listing replay assertions

- **Status:** Proposed for M1 review
- **Date:** 2026-11-10

## Context

Listing and membership histories retain explicit assertions and their complete
metadata/receipt/payload graph. Consumers still need an immutable query that pins
both record sets and independently selects their revisions at one effective and
decision time. A stored report must be recomputed, rather than trusted as supplied
membership or silently dropping unresolved securities.

## Decision

`data.universe_listing_replays.UniverseListingReplayManifest` takes explicit
built-in tuple/list collections `listing_history_record_sha256s` and
`membership_history_record_sha256s`, snapshots and sorts distinct lowercase
digests, and exposes immutable tuples. Invalid containers, entries and duplicate
digests reject before dependency reads. The manifest also pins exact nonblank
`universe_id`, `membership_source_id`, `listing_source_id`, `venue`, `effective_at`
and `decision_at`. Universe identity uses the existing public
`membership_observation_id` rule, preserving its entire suffix and whitespace.

Query times require standard aware `datetime` values with UTC, standard fixed
offsets or reopenable keyed `ZoneInfo`. A key must reproduce the instant's offset
and name. UTC roundtrips reject nonexistent civil times before normalization;
both valid folds remain distinct. Unsupported subclasses/tzinfo, naive/date
values and UTC overflow reject as `ValueError`. Values normalize to UTC with
`fold=0` and require effective time no later than decision time. This scalar
persistence boundary leaves existing in-memory query contracts unchanged and
does not pin the full timezone database.

Frozen `UniverseListingReplay(manifest, listing_records, membership_records)`
requires typed immutable record tuples corresponding exactly to each sorted
digest tuple. It constructs existing `ListingCatalog` and `UniverseCatalog` over
every supplied record before any filtering or mapping. Duplicate version IDs,
ranks or contradictory availability fail globally, including irrelevant/future
histories and conflicting interval assertions against one version. Equal IDs or
ranks on distinct keys remain valid. Its `result: UniverseListingResult` is
computed only (`init=False`) by `UniverseCatalog.listings_at` with the manifest's
exact filters and common effective/decision instants. All records remain available
for provenance. Direct construction/encoding checks consistent assertions, not
archive existence or source truth. An empty standalone build checks the archive
argument type without checking current filesystem liveness; put/get check the
current root through their outer archive I/O.

Schema 1 is sorted-key compact ASCII JSON, escaped non-ASCII and no newline:
`schema_version`, `replay_policy_id="historical-universe-listing-replay-v1"`,
`manifest`, and `report`. Manifest contains the eight fields above, with six-digit
UTC `Z` times. Report has only `membership_selections` and `listing_lookups`.
Membership rows have `membership_history_record_sha256` and nullable zero-based
`matched_interval_index`; they include selected negatives in stable-security
order. Listing rows have `security_id`, nullable
`listing_history_record_sha256` and nullable `matched_interval_index`, exactly one
per asserted member in member order. Indices refer to original ordered history
tuples, not chronologically sorted copies. Null membership index retains selected
negative provenance. Null listing digest means no eligible supplied history;
selected digest with null index means a selected negative mapping. Positive,
unresolved and member arrays/counts derive from the result and are not duplicated.
Version association always uses `(ObservationKey, version_id)`, never ID alone.

`build_universe_listing_replay(archive, manifest)` requires a real archive argument
even for empty collections and loads every history through its typed get API, verifying
all metadata, accepted receipts and payloads. `encode_universe_listing_replay`
writes the computed report. `decode_universe_listing_replay(payload, archive)`
strictly validates complete manifest/report shape, types, nonnegative standard
integer indices (not bool/float), duplicate keys, canonical times/order and bytes
before dependency access where possible. Selected digests must belong to their
manifest without repeats; listing IDs must be unique/sorted and their count equal
matched membership count. Membership-row security order requires dependencies.
It reloads every dependency, reconstructs both catalogs and the result, then
requires complete recomputed byte equality.
Valid changed query/dependencies with their correct recomputed report are new
assertions, not evidence of source parsing or authenticity.

`LocalRawArchive.put_universe_listing_replay(manifest)` verifies all dependencies
and publishes one canonical query/report object last, returning its digest.
`get_universe_listing_replay(digest)` verifies and reopens the whole graph.
`UniverseListingReplayFormatError` is a standalone codec `ValueError`;
`UniverseListingReplayMissingError` and `UniverseListingReplayCorruptError` inherit
`RawArchiveError`. History, metadata, receipt, payload and filesystem dependency
errors propagate unchanged. No partial result, fallback, member drop or repair
is permitted. Wrong typed references fail through the requested typed API.

ADR 0009's trusted POSIX, verified no-replace publication and failure limits apply.
Pre-publication faults expose no replay object. Post-link cleanup/directory-close
faults may raise with a complete object already published; retry verifies it but
does not remove abandoned staging files. No fsync, crash durability, transaction,
index/discovery, recovery or new dependency/service is added.

## Limits and reference evidence

The policy and recomputed report detect format/query drift, not authenticated
executables or complete research reproducibility. Code/config/environment fields
are omitted: unverified caller references would mislead. This is no evaluable
snapshot, complete environment collector, provider integration, coverage/source
proof, market bar/action/transform pipeline, operational processing gate, strategy
evaluation or financial/trading behavior. All M1 acceptance gates remain open.

Independent literal bytes/hash/report pin dependency IDs and fresh-archive replay.
Reference cases cover independent correction cutoffs, key-scoped empty/negative
replacements, missing versus selected-negative mappings, unresolved delistings,
ticker reuse, equal symbols on distinct stable IDs and original interval indices.
Other acceptance cases cover empty/invalid archives, immutable sorted membership,
global catalog contradictions, malformed/rehashed/noncanonical reports, every
missing/corrupt/wrong-typed dependency and pre/post-publication failure/retry.

## Alternatives

Separate listing and membership inventories add no consumer behavior needed here.
Trusting stored results, deduplicating ambiguous histories or filtering before
catalog validation conceals errors. Current tickers cannot substitute for stable
IDs. Recomputing the existing join over explicit immutable dependencies is the
smallest auditable consumer slice without introducing a pipeline framework.
