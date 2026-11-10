# ADR 0015: Persisted universe-membership history assertions

- **Status:** Proposed for M1 review
- **Date:** 2026-11-10

## Context

The existing `MembershipHistory` contract retains source-specific complete
membership replacements in memory. Observation metadata and listing histories
now persist with exact dependency references, but their stable-ID universe joins
cannot yet reopen the membership interval assertions. Persistence must retain the
whole universe identity and negative replacement provenance without treating
listing status as membership or inventing proof of source parsing.

## Decision

`data.membership_records.MembershipHistoryRecord(history, observation_record)`
requires an explicit `MembershipHistory` and `ReceiptLinkedVersion`. It normalizes
the supplied version through the public ADR 0012 `ReceiptLinkedVersion` boundary
using the actual referenced receipt digest and requires exact canonical
observation-record byte equality. This binds all key, rank, provenance and time
assertions rather than silently discarding a supplied version. The returned
record retains the normalized history and its metadata/receipt provenance.

`MembershipHistory` is reconstructed with the exact `universe_id` and ordered
`MembershipInterval` tuple. `membership_observation_id` uses its entire nonblank
suffix after the fixed `universe-membership-history:` prefix. Colons and
leading/trailing whitespace are retained, without splitting, stripping, case
normalization or ticker-derived identity. All existing half-open interval,
no-overlap and complete per-security/source/universe replacement semantics remain.
An explicit empty replacement changes only that key's assertion and keeps selected
negative provenance. Listing endings neither remove members nor supply a new
membership end-reason field.

The existing interval constructor has already normalized valid aware endpoints
to UTC. The new persistence boundary requires standard UTC `datetime` endpoints,
normalizes `fold=0` and serializes six fractional digits with `Z`. It does not
claim to recover an original zone representation. Existing in-memory contracts
are unchanged. Tuple order is preserved in bytes, not sorted; a reordered valid
assertion receives a different digest.

Schema version 1 is canonical ASCII JSON with sorted keys, compact separators,
escaped non-ASCII and no trailing newline. It contains `schema_version`,
`membership_policy_id="receipt-linked-membership-history-v1"`, exact `universe_id`,
`observation_record_sha256`, and ordered `intervals`. Each interval has only
`effective_from` and nullable `effective_until`. The version remains in its pinned
metadata dependency. The independent literal membership receipt, observation and
history fixtures pin exact schema/bytes and the full universe key.

`build_membership_history_record(archive, history, observation_record_sha256)`
loads the exact existing observation record through `get_observation_record`,
verifying metadata, accepted receipt and payload, then checks supplied-history
correspondence. `LocalRawArchive.put_membership_history_record(history, digest)`
verifies dependencies before publishing one membership assertion last and returns
its separate SHA-256. It creates no metadata, receipt or payload.
`get_membership_history_record` and `decode_membership_history_record(payload,
archive)` strictly reopen that graph and reconstruct the existing universe
history contract. Wrong schema/policy/types, unknown/missing fields, duplicate
keys, noncanonical UTC spellings or bytes reject. An outer universe that does not
match the pinned metadata's full observation key also rejects.

Direct construction/encoding checks shape and correspondence, not dependency
existence or source truth. Valid interval changes, a compatible new metadata
reference, or a jointly changed universe/reference create new assertions. Their
hashes do not authenticate parsing, coverage, rights or identity. Conflicting
histories can reference a version; a future consumer collection boundary must
reject ambiguous catalog identities. Policy meaning changes require an explicit
version decision.

## Failures and limits

Invalid API arguments or supplied-version mismatch raise `ValueError`.
`MembershipHistoryRecordFormatError` is the standalone codec `ValueError` subtype;
`MembershipHistoryRecordMissingError` and `MembershipHistoryRecordCorruptError`
inherit `RawArchiveError`. Metadata, receipt, payload and filesystem dependency
failures propagate unchanged. There is no fallback, partial result or repair.

ADR 0009's trusted local POSIX, verified no-replace publication and failure limits
apply. Pre-publication failure exposes no new membership object; cleanup or
directory-close failure can raise after a complete object is linked. Retry
verifies it but does not remove abandoned staging files. No fsync, crash
durability, crash transaction, global index, discovery or recovery is added.
Callers retain membership digests.

This slice adds no separate inventory, query/replay artifact, evaluable dataset
snapshot, source authentication, provider acquisition or integration, coverage
guarantee, full security master, new dependency/service or financial/trading
behavior. Reopened membership and listing histories compose through existing
catalogs with independent release cutoffs and stable-ID joins; that composition
does not prove real-world universe completeness. All M1 gates remain open.

## Reference evidence

Tests must pin a fresh literal receipt/metadata/membership hash chain with the
exact universe suffix, then independently specify entry/exit, late corrections,
negative replacements and key isolation after reopen. Cross-module cases use
reopened listing records to prove independent release cutoffs, unresolved delisted
members, ticker reuse without rebinding and negative mapping provenance. Version
and universe mismatches, typed/canonical boundaries, malformed/rehashed JSON and
every missing/corrupt dependency reject. Injected pre/post-publication faults
retain the existing archive contract. Local results establish neither provider
acceptance, remote CI nor milestone approval.

## Alternatives

Stripping or splitting universe IDs changes their identity. Inferring membership
from current listings loses delisted members. A record that drops a mismatched
supplied version conceals caller errors; importing listing end reasons invents a
new membership convention. A pinned metadata dependency plus the existing
membership constructors preserves the narrow assertion boundary without adding
unused inventories or provider-specific parsing assumptions.
