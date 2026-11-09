# ADR 0007: In-memory historical security listing histories

- **Status:** Proposed for M1 review
- **Date:** 2026-11-09

## Context

A ticker is a display symbol, not a permanent security identity. A source may
announce a future rename, later correct an old delisting date, or reuse a symbol
for another security. Effective dates alone leak corrections into old decisions;
release dates alone cannot describe which listing was effective at a past instant.

## Decision

`data.listings` adds immutable `ListingInterval` and `ListingHistory` records and
an in-memory `ListingCatalog`. Each history binds its intervals to one validated
`ObservationVersion`. The fixed `ObservationKey` scheme is
`(security_id, source_id, observation_id="listing-history")`. One version covers
the complete source-specific listing history of that stable security across all
venues. Source adapters must map their revision order to the existing integer
rank contract, preserve stable security/issuer identities, and document their
mapping. Symbols never generate or replace stable IDs. No ID registry is added.

Each version is a complete replacement, not a delta. Interval input must be a
tuple or list and is snapshotted to an immutable tuple. Other container types
reject, including empty strings, bytes, mappings, and sets: they cannot silently
assert an empty replacement. An explicit empty tuple/list replacement is valid.
Catalog history input may be an iterable of histories, but text, byte sequences,
and mappings reject even when empty rather than silently becoming an empty catalog.
Removing an interval changes that version's assertion; it does not delete
older histories or fall back to them. A truncated provider response cannot safely
be treated as a complete replacement: an adapter must establish and document
scope first. This module cannot authenticate that assertion. Provider retractions
remain unsupported under `ObservationVersion`; an empty history is not a new
retraction protocol and does not invalidate a revision's provenance.

Two explicit temporal axes govern queries:

1. `decision_at` selects the latest historically usable revision through
   `VersionCatalog`, using the inclusive maximum of publication and provider
   availability, source rank tie-breaking, and security/source partitioning.
2. `effective_at` selects an interval from that revision, with
   `effective_at <= decision_at` required. All interval and query comparisons use
   UTC instants. Effective queries into the future are rejected even for an
   already announced event; this API answers historical/current identity only.

`ListingInterval` retains exact issuer ID, symbol, venue, and currency text.
Nonblank identifiers are required; there is no trimming, uppercasing, punctuation
rewrite, ticker heuristic, exchange equivalence, FX convention, or issuer merge.
Intervals use `[effective_from, effective_until)` with a strictly later optional
end. Start is inclusive and end exclusive; adjacent intervals are valid. Any
overlap within one security/venue/history is rejected, including identical
duplicates. Simultaneous listings on different venues are allowed. Each ended
interval requires a nonblank source-defined `end_reason` (for example `delisted`
or `symbol_changed`); an open interval forbids a reason. This preserves explicit
source assertions without introducing an unapproved provider-independent reason
taxonomy. Ended/delisted intervals remain queryable in historical versions.

Endpoints and query timestamps must be aware real instants. A UTC roundtrip must
preserve civil time and offset, rejecting nonexistent spring DST times while
allowing both valid fall folds. Endpoints and query timestamps normalize to UTC.
The history boundary also checks every supplied timestamp in its bound metadata
for nonexistent civil times; `core.time` and `data.versions` retain their existing
contracts. Selected metadata itself is preserved unchanged.

`listing_at(security_id, source_id, venue, effective_at, decision_at)` returns one
match or an absent match. `resolve_symbol_at(symbol, source_id, venue,
effective_at, decision_at)` independently selects each eligible security history
in that exact source before matching exact venue and symbol. Multiple matching
securities raise `ValueError`; there is no rank comparison across securities and
no silent winner. Future-ineligible histories never create ambiguity.

`ListingQueryResult` retains exact query identifiers, UTC effective/decision
timestamps, a `ListingMatch` containing interval and selected version when
present, and all eligible selected versions inspected even when no match exists.
Symbol query versions are ordered deterministically by stable security ID. A
missing interval in an eligible history differs from no eligible history, but
neither is a claim that the source or catalog is complete. These query records
are result containers; constructing one directly does not validate a dataset.

## Provenance and limitations

Source URI, license ID, checksum, revision ID/rank, and availability remain on
every selected version, including absent matches after an empty replacement.
The module cannot authenticate IDs, evidence, release times, complete history
scope, revision semantics, licenses, or the checksum against bytes. Adapters must
use the raw admission boundary for uncertain release claims and verify the
relationship of payload and metadata; no canonical payload serialization or hash
verification is implemented here. Historical source replay ignores later backfill
ingestion, as ADR 0002 requires. These APIs do not establish actual operational
ingestion/processing or authorize any execution.

No dependencies, provider, persistent store, universe membership/join, corporate
action processing, dataset snapshot, accounting convention, or trading path are
added. The owner still needs to review this key/scope convention and source
identity/end-reason mappings before a provider integration. A security master
requires more than this in-memory identity slice; all M1 gates remain open.

## Reference evidence

Hand-specified contract cases cover initial listing and adjacent rename
boundaries, future announcements, delisting survival and exact end, ticker reuse,
late corrections, complete replacements removing intervals without fallback,
same-symbol ambiguity only among eligible selected histories, source/venue/symbol
partitioning, rank ties and contradictions, overlap rejection, explicit end
reasons, immutable payloads, backfill ingestion, both release gates, real DST
folds/offsets, and naive/nonexistent timestamps. Local tests alone do not establish
CI, independent review, source authenticity, or M1 acceptance.

## Alternatives

A latest-current ticker dictionary loses historical identities. Filtering all
versions by effective time before selecting a revision resurrects intervals
removed by a correction. Delta histories require an amendment/retraction merge
protocol and additional provenance rules; complete replacements provide the
smaller auditable contract for this slice.
