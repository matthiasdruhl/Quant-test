# ADR 0012: Receipt-linked observation-version records

- **Status:** Proposed for M1 review
- **Date:** 2026-11-10

**Subsequent extension:** [ADR 0013](0013-version-catalog-inventories.md) adds
explicit immutable collections of these observation-record digests and combined
catalog validation. The individual-record scope below remains unchanged; neither
extension authenticates source assertions or creates an evaluable dataset snapshot.

## Context

`ObservationVersion` contains explicit source-version assertions but currently
exists only in memory. Raw admission receipts persist source claims and bytes,
without granting catalog eligibility. Retaining a supplied version together with
its exact raw evidence reference needs a separate, verified persistence boundary;
an accepted receipt must not silently become a validated observation.

## Decision

`data.observation_records.ReceiptLinkedVersion` is a frozen record containing a
caller-supplied `ObservationVersion` and one lowercase `receipt_sha256`.
`build_observation_record(archive, version, receipt_sha256)` requires an existing
`LocalRawArchive`, validates the supplied metadata, reopens that exact receipt and
payload, and requires accepted admission. Key, version ID, source URI, license ID,
payload digest and all four availability fields must match. Text is exact,
including whitespace; times compare by UTC instant and unknown event times match
only unknown event times. Revision rank remains the caller's explicit source-order
assertion, not a value inferred from a receipt, hash or timestamp. Existing
retractions remain unsupported. The persisted rank must be a standard `int`, not
`bool`, float or an integer subclass; the existing in-memory constructor is not
changed by this narrower encoding boundary.

The persistence boundary accepts standard `datetime` values with UTC, standard
fixed-offset `timezone`, or reopenable keyed `ZoneInfo` zones. Other datetime/date
subclasses and timezone implementations reject here without changing existing
in-memory contracts. Each supplied civil time must roundtrip through UTC with the
same civil value and offset; nonexistent DST gap values reject before
normalization. A keyed zone must reproduce its offset/name using the current zone
rules. Both real DST folds remain distinct UTC instants. The returned version uses
UTC timestamps with `fold=0`; equivalent aware representations yield identical
metadata bytes. Its raw receipt independently retains original precision,
timezone, fold and text under ADR 0010. Normalization is a metadata-storage
representation decision, not a new availability estimate or accounting convention.

`encode_observation_record` serializes a supplied assertion as schema-version-1
canonical ASCII JSON: sorted keys, compact separators, escaped non-ASCII, no
trailing newline. The object contains `schema_version`,
`linkage_policy_id="receipt-linked-observation-v1"`, `receipt_sha256`, and the full
explicit `version` fields. Availability fields use exact UTC ISO timestamps with
six fractional digits and `Z`; only `event_at` permits null. No rank, provenance,
identity or availability is omitted merely because the receipt repeats it.
The independent literal `tests/fixtures/observation-record-v1.json` pins bytes and
schema. Direct record construction/encoding validates shape, not dependencies.

`decode_observation_record(payload, archive)` strictly parses schema/policy/types,
rejects duplicate/unknown/missing fields and noncanonical bytes, rebuilds the
supplied version, then repeats the receipt/payload and shared-field checks.
Rehashing edited metadata cannot make inconsistent linkage pass. Successful
decoding does not authenticate an adapter's assertions or the source's rank.

`LocalRawArchive.put_observation_record(version, receipt_sha256) -> str` verifies
existing dependencies before publishing one canonical metadata object last under
its own SHA-256. It creates no receipt or payload. `get_observation_record(digest)`
verifies metadata bytes and strictly reopens every dependency before returning the
record. The existing `put_version/get_version` APIs still address payload bytes;
their contracts are unchanged. Callers retain metadata digests externally.

## Failures and limits

Invalid arguments, unsupported boundary types, quarantined receipts or mismatched
assertions raise `ValueError`; standalone decoding wraps malformed or inconsistent
metadata as `ObservationRecordFormatError`, a `ValueError` subtype.
`ObservationRecordMissingError` and `ObservationRecordCorruptError` inherit
`RawArchiveError`. Referenced receipt, payload and filesystem errors propagate
unchanged. No operation falls back to an older version or repairs corrupt bytes.

ADR 0009's trusted local POSIX root, no-replace protocol and failure limits apply.
Dependency or pre-link publication failure exposes no new metadata object.
Cleanup/directory-close failure can raise after a complete linked object exists;
retry verifies it but does not remove abandoned staging files. No fsync, crash
durability, multi-object crash transaction, index, discovery, recovery or garbage
collection is added.

This persists explicit metadata assertions and verifies syntactic linkage. It
authenticates neither source evidence, stable identity, license rights, revision
semantics nor completed processing. It does not promote raw receipts, create a
catalog inventory or dataset snapshot, select an as-of revision, or add provider
ingestion, normalized listing/membership persistence, coverage, dependencies,
services, financial conventions or trading behavior. All M1 gates remain open.

## Reference evidence

Tests must pin independent literal bytes/hash, every shared-field mismatch,
accepted/quarantined outcomes, unknown events, equivalent offsets, both real folds,
nonexistent civil times and unsupported types. Strict rehashed schema/policy/type
and canonical-byte tampering must reject. Missing/corrupt records, receipts and
payloads fail explicitly. Injected dependency/pre-publication failures and
post-publication cleanup failures retain existing archive semantics. Composition
with `VersionCatalog` must preserve historical release boundaries without implying
source authentication or operational eligibility. Local checks alone do not prove
remote CI, independent review, provider readiness or milestone acceptance.

## Alternatives

Deriving a version from accepted admission would hide missing source-order and
provenance validation. Serializing versions without a receipt reference would lose
the auditable raw linkage. A mutable metadata database or automatic archive scan
would enlarge this slice unnecessarily. An additive content-addressed assertion
record reuses the existing storage/failure boundary and leaves catalog inventories
and evaluable snapshots to separate reviewed slices.
