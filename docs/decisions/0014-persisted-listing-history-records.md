# ADR 0014: Persisted listing-history assertions

- **Status:** Proposed for M1 review
- **Date:** 2026-11-10

## Context

Historical listing identity already has an in-memory complete-replacement
contract. ADR 0012 persists explicit observation versions and their raw receipt
linkage, but the normalized listing intervals supplied by a caller cannot yet be
retained and reopened with that exact version. A generic codec cannot prove those
intervals were parsed correctly from a provider payload; that remains adapter and
independent fixture work.

## Decision

`data.listing_records.ListingHistoryRecord(history, observation_record)` is frozen.
It requires an explicit `ListingHistory` and `ReceiptLinkedVersion`. It normalizes
the supplied history version through the public ADR 0012 `ReceiptLinkedVersion`
boundary using the referenced record's actual receipt digest. The existing
`encode_observation_record` bytes must match the referenced record exactly. This
checks every version field, including rank, key, provenance, unknown event time,
release/ingestion instants and unsupported retractions, without importing private
normalization helpers or discarding a different supplied version.

The returned history uses that normalized version. Intervals are reconstructed
through the existing `ListingInterval` and `ListingHistory` constructors, retaining
their fixed `listing-history` key, all-venue complete-replacement assertion,
half-open UTC boundaries, overlap checks and end-reason requirements. Issuer,
symbol, venue, currency and end-reason text remain exact; no reason taxonomy,
symbol mapping or venue equivalence is introduced. An explicit empty history
remains a negative replacement assertion, never an inferred deletion.

The existing interval constructor has already normalized valid aware endpoints
to UTC. This persistence boundary requires standard `datetime` endpoint values,
uses `fold=0` and stores six fractional digits with `Z`. It does not recover or
claim to revalidate an original timezone representation lost by the existing
constructor. Existing in-memory timestamp/container contracts remain unchanged.
Interval tuple order is preserved in bytes, not sorted: reordering a caller's
assertion creates a different record digest even when queries have the same
result. No new financial or effective-time convention is selected.

Schema version 1 is canonical ASCII JSON with sorted object keys, compact
separators, escaped non-ASCII and no trailing newline. It contains
`schema_version`, `listing_policy_id="receipt-linked-listing-history-v1"`, the
exact `observation_record_sha256`, and `intervals`. Every interval contains
`issuer_id`, `symbol`, `venue`, `currency`, `effective_from`, `effective_until` and
`end_reason`; the last two are nullable under the existing interval contract.
The full version assertion lives in its pinned metadata dependency rather than
being duplicated. The returned record retains that dependency and its receipt
provenance. Direct construction/encoding checks correspondence and shape, not
archive existence or external truth.

`build_listing_history_record(archive, history, observation_record_sha256)` loads
the exact existing observation record through `get_observation_record`, verifying
its metadata, accepted receipt and payload, before checking supplied history
correspondence. `LocalRawArchive.put_listing_history_record(history, digest)`
publishes one canonical listing record last and returns its separate SHA-256. It
creates no observation record, receipt or payload. `get_listing_history_record`
and `decode_listing_history_record(payload, archive)` strictly reopen the version
dependency and reconstruct the interval assertion. Invalid schemas, policies,
field sets, duplicate keys, types, time spellings and noncanonical bytes reject.
The independent literal `tests/fixtures/listing-history-record-v1.json` pins schema
and bytes. Policy meaning changes require an explicit version decision.

Changing valid intervals, their order, or a reference to another fully valid
listing-history version can create a new assertion. Rehashing malformed data or
an inconsistent supplied version cannot make it valid, but content addressing
does not authenticate source parsing or make asserted intervals true. Multiple
conflicting histories can reference the same version; a future collection
boundary must reject conflicting catalog identities rather than silently choose.

## Failures and limits

Invalid API arguments or supplied-version mismatch raise `ValueError`.
`ListingHistoryRecordFormatError` is the standalone decoding `ValueError` subtype.
`ListingHistoryRecordMissingError` and `ListingHistoryRecordCorruptError` inherit
`RawArchiveError`; referenced metadata, receipt, payload and filesystem failures
keep their existing types. Reads fail without fallback; corrupt objects are not
repaired. Put keeps the existing base publication error types.

ADR 0009's trusted local POSIX assumptions and verified no-replace protocol apply.
Dependency/pre-link failure exposes no new listing record. Cleanup/directory-close
failure can raise after a complete object is linked; retry verifies it without
removing abandoned staging files. No fsync, crash durability, crash transaction,
discovery, mutable index or recovery is added. Callers retain listing digests.

This slice persists one caller's complete listing-history assertion. It does not
authenticate identity, parsing, source scope, revision order, timing or rights.
It adds no listing catalog inventory, membership serialization, query/dataset
snapshot, provider integration, coverage guarantee, full security master,
processing evidence, dependency/service or financial/trading behavior. Reopened
histories may compose with the existing `ListingCatalog`; that composition does
not establish real-world source completeness. All M1 gates remain open.

## Reference evidence

Tests must independently pin canonical bytes/hash and temporal expectations for
rename/delist boundaries, late corrections, negative replacements, ticker reuse
and multi-venue histories after reopen. Every supplied-version mismatch must
reject, including rank and exact text; equivalent real offsets follow ADR 0012.
Strict interval/schema/type/canonical-byte tampering and broken dependencies fail.
Valid changed assertions remain distinct without any source-truth claim. Injected
pre/post-publication failures retain existing archive semantics. Local checks do
not establish provider acceptance, remote CI or milestone approval.

## Alternatives

Promoting raw receipts would hide missing version validation. Storing only
intervals without a pinned metadata dependency would lose historical provenance.
Dropping a mismatched supplied history version during encoding would hide caller
errors. Reusing the public metadata boundary and a pinned dependency keeps the
assertion explicit without duplicating version codecs or enlarging this slice
into a catalog, provider parser or identity convention change.
