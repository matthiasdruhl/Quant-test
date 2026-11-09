# ADR 0008: In-memory point-in-time universe membership and listing join

- **Status:** Proposed for M1 review
- **Date:** 2026-11-09

## Context

Historical universe membership cannot be inferred from today's listed symbols.
A source can publish a removal after its effective date or later correct a past
membership interval. The listing mapping can have a different release schedule
from membership. Selecting either source using effective time, or using the
other source's release time, can leak information or discard historical members.

## Decision

`data.universes` adds immutable `MembershipInterval` and `MembershipHistory`
records, an in-memory `UniverseCatalog`, and historical query result containers.
Each history covers one stable security/source/universe and binds all its
membership intervals to one validated `ObservationVersion`. Its fixed key scheme
is `(security_id, source_id, observation_id="universe-membership-history:" +
universe_id)`. `membership_observation_id` constructs that exact observation ID.
The prefix is fixed; the entire remaining suffix is the exact nonblank universe
ID, including any colons. No splitting, normalization, ticker inference, or ID
registry is introduced. Different universe IDs cannot collide under this scheme.
Adapters must document stable identity mapping, universe scope and revision ranks.

Every revision asserts a complete replacement history for that key, not a delta
or a snapshot of every security in a universe. An explicit empty tuple/list
asserts no intervals for this security in this revision. Omitted intervals never
fall back to older revisions. Unmentioned security keys are not implicitly
deleted; adapters must provide their own explicit per-security replacements.
Truncated provider responses cannot safely assert complete histories. This type
does not authenticate the adapter's complete replacement assertion.

Intervals use real, aware UTC `[effective_from, effective_until)` boundaries.
Start is inclusive and end exclusive. A supplied end must follow start. Duplicate
and overlapping intervals within one history reject; adjacency is permitted.
Interval lists are copied to tuples, and frozen records preserve immutable inputs.
Only tuple/list interval containers are accepted, including for empty replacement;
empty text, bytes, mappings or sets cannot silently erase a history. Catalogs
snapshot iterable histories, rejecting text, byte sequences, mappings and
unvalidated members even when an invalid container is empty. No new membership
end-reason taxonomy or financial/accounting convention is introduced.

`members_at(universe_id, source_id, effective_at, decision_at)`:

1. Validates nonblank exact source/universe identifiers and real aware times,
   requiring `effective_at <= decision_at`.
2. Independently selects each security's latest eligible complete history in that
   exact universe/source partition through `VersionCatalog`. Eligibility uses
   `max(published_at, source_available_at) <= decision_at`; source ranks resolve
   equal usability, and ambiguous duplicates/contradictory ranks reject.
3. Filters only that selected revision's intervals by effective time.

`MembershipQueryResult` retains UTC effective/decision timestamps, exact source
and universe, selected versions for every eligible history inspected, and matched
membership intervals with their versions. Its `member_ids` are asserted stable
IDs, sorted deterministically by security ID. Histories without an effective
interval remain in `selected_versions`, including explicit empty replacements.
No eligible history differs from an eligible negative assertion; neither proves
real-world absence, provider coverage, or universe completeness. An end to listing
does not end or remove a membership assertion.

`listings_at(universe_id, source_id, listing_catalog, listing_source_id, venue,
effective_at, decision_at)` joins each asserted stable member ID using
`ListingCatalog.listing_at` and the explicitly chosen exact listing source/venue.
Every lookup receives the same E/D as membership. Membership and listing metadata
independently apply their own publication/provider cutoffs against D, including
when mapping corrections become usable later than membership. Stable IDs are
never re-resolved using today's ticker. Mapping absence, ended listing, or a
selected replacement omitting a listing leaves an explicit unresolved member.

`UniverseListingResult` retains the membership result and one `ListingQueryResult`
per asserted member, in the same security-ID order. `matches` returns mapped
intervals with their selected versions; `unresolved_member_ids` names every
unmatched member. Per-member listing results retain selected negative mapping
versions or an empty selection if no history is eligible. Membership negative
context remains in the nested membership result. Both sources' URI, license,
checksum, revision rank/ID and availability are therefore retained on versions.
Result records are output containers, not validated datasets when constructed
directly.

The join preserves distinct stable member IDs even if their display symbols are
identical. It makes no ticker uniqueness claim and does not choose between IDs.
`ListingCatalog.resolve_symbol_at` remains the explicit symbol lookup boundary
and raises on ambiguous eligible symbol mappings under ADR 0007. Overlapping
listing intervals for one security/venue still fail that catalog's validation.
Disjoint effective histories may reuse a ticker for different stable IDs.

Interval, query and bound metadata timestamps must survive a UTC roundtrip to
the same civil time and offset. Nonexistent spring DST gap times reject; valid
fall folds compare as separate UTC instants. Intervals and query times normalize
to UTC; selected metadata remains unchanged. Existing core/time, revision and
listing contracts are unchanged.

## Provenance and limitations

Raw missing/uncertain availability must use `data.admission` quarantine and cannot
enter these catalogs. The validated metadata type cannot authenticate evidence,
complete history scope, identity, revision ordering, licenses, or payload hashes;
those remain adapter responsibilities. No canonical payload hashing is added.
Historical source replay ignores later ingestion backfills, as ADR 0002 requires.
It does not establish local processing or authorize operational consumption.

This is one in-memory membership/join slice. No provider integration, persistent
storage, OHLCV, corporate action processing, dataset snapshot, source coverage
report, strategy, deployment or trading path is added. No dependencies are added.
All M1 gates remain open for their complete CI, independent review and acceptance
evidence. ADR 0007 remains the source of listing/end-reason conventions.

## Reference evidence

Hand-specified cases cover entry/exit and adjacency boundaries, delayed removal
publication, late membership corrections, empty complete replacements without
fallback, negative provenance versus no eligible versions, delisted members as
unresolved joins, ticker reuse preserving stable IDs, independent mapping and
membership release cutoffs, later mapping replacements, exact source/universe/
venue isolation, same-symbol stable-ID preservation and ambiguous symbol lookup,
duplicate ranks/IDs and overlaps,
unknown availability quarantine, invalid empty containers, backfill ingestion,
input copying, deterministic ordering, and DST fold/gap/naive timestamp rejection.
Local tests do not establish source authenticity, remote CI or independent review.

## Alternatives

Current-symbol filters introduce survivorship bias and symbol reuse errors.
Filtering intervals before revision selection resurrects facts removed by later
eligible corrections. Delta membership updates require an amendment/retraction
merge protocol. Complete per-security replacements provide the narrower contract
compatible with the existing revision and listing catalogs.
