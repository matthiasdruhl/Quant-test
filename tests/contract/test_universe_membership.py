"""Hand-specified membership and temporal join references, not provider coverage."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from quant_test.core.time import InformationAvailability
from quant_test.data.admission import (
    QuarantinedAvailability,
    RawAvailability,
    RawTimestampClaim,
    TimestampStatus,
    admit_availability,
)
from quant_test.data.listings import (
    LISTING_HISTORY_OBSERVATION_ID,
    ListingCatalog,
    ListingHistory,
    ListingInterval,
)
from quant_test.data.universes import (
    MembershipHistory,
    MembershipInterval,
    UniverseCatalog,
    membership_observation_id,
)
from quant_test.data.versions import ObservationKey, ObservationVersion


def t(day: int, hour: int = 0) -> datetime:
    return datetime(2025, 1, day, hour, tzinfo=UTC)


INITIAL_START = t(1)
INITIAL_MEMBERSHIP = (MembershipInterval(INITIAL_START),)


def version(
    identity: str,
    rank: int,
    usable: datetime,
    observation_id: str,
    *,
    security: str = "security-a",
    source: str = "membership-source",
    published: datetime | None = None,
) -> ObservationVersion:
    return ObservationVersion(
        ObservationKey(security, source, observation_id),
        identity,
        rank,
        InformationAvailability(None, usable if published is None else published, usable, t(31)),
        f"https://reference.example/{identity}",
        "reference-fixture-license",
        "a" * 64,
        False,
    )


def history(
    identity: str = "m1",
    rank: int = 1,
    usable: datetime = INITIAL_START,
    intervals: tuple[MembershipInterval, ...] = INITIAL_MEMBERSHIP,
    *,
    security: str = "security-a",
    source: str = "membership-source",
    universe: str = "universe-a",
    published: datetime | None = None,
) -> MembershipHistory:
    return MembershipHistory(
        universe,
        version(
            identity,
            rank,
            usable,
            membership_observation_id(universe),
            security=security,
            source=source,
            published=published,
        ),
        intervals,
    )


def listing(
    identity: str = "l1",
    rank: int = 1,
    usable: datetime = INITIAL_START,
    *,
    security: str = "security-a",
    symbol: str = "OLD",
    start: datetime = INITIAL_START,
    end: datetime | None = None,
    source: str = "listing-source",
    venue: str = "XNYS",
    published: datetime | None = None,
    empty: bool = False,
) -> ListingHistory:
    return ListingHistory(
        version(
            identity,
            rank,
            usable,
            LISTING_HISTORY_OBSERVATION_ID,
            security=security,
            source=source,
            published=published,
        ),
        ()
        if empty
        else (
            ListingInterval(
                "issuer-a", symbol, venue, "USD", start, end, None if end is None else "delisted"
            ),
        ),
    )


def members(catalog: UniverseCatalog, effective: datetime, decision: datetime) -> Any:
    return catalog.members_at("universe-a", "membership-source", effective, decision)


def joined(
    catalog: UniverseCatalog,
    listings: ListingCatalog,
    effective: datetime,
    decision: datetime,
) -> Any:
    return catalog.listings_at(
        "universe-a", "membership-source", listings, "listing-source", "XNYS", effective, decision
    )


def test_inclusive_entry_exclusive_exit_and_adjacent_intervals() -> None:
    record = history(intervals=(MembershipInterval(t(3), t(10)), MembershipInterval(t(10), t(20))))
    catalog = UniverseCatalog([record])
    for effective, expected in [(t(2), ()), (t(3), ("security-a",)), (t(20), ())]:
        result = members(catalog, effective, t(20))
        assert result.member_ids == expected
        assert result.selected_versions == (record.version,)
    boundary = members(catalog, t(10), t(20))
    assert len(boundary.members) == 1
    assert boundary.members[0].interval.effective_from == t(10)
    assert boundary.members[0].version is record.version


def test_removal_published_later_does_not_change_prior_decision() -> None:
    initial = history()
    removal = history("m2", 2, t(15), (MembershipInterval(t(1), t(10)),), published=t(20))
    catalog = UniverseCatalog([removal, initial])
    before = members(catalog, t(12), t(19))
    after = members(catalog, t(12), t(20))
    assert before.member_ids == ("security-a",) and before.selected_versions == (initial.version,)
    assert after.member_ids == () and after.selected_versions == (removal.version,)
    assert members(catalog, t(9), t(20)).member_ids == ("security-a",)


def test_late_correction_can_add_past_membership_without_leaking() -> None:
    initial = history(intervals=(MembershipInterval(t(10)),))
    correction = history("m2", 2, t(20), (MembershipInterval(t(5)),))
    catalog = UniverseCatalog([correction, initial])
    assert members(catalog, t(7), t(19)).member_ids == ()
    corrected = members(catalog, t(7), t(20))
    assert corrected.member_ids == ("security-a",)
    assert corrected.selected_versions == (correction.version,)


@pytest.mark.parametrize("reverse", [False, True])
def test_complete_replacement_and_ineligible_absence_keep_distinct_provenance(
    reverse: bool,
) -> None:
    initial = history()
    removal = history("m2", 2, t(21), ())
    records = [initial, removal]
    catalog = UniverseCatalog(reversed(records) if reverse else records)
    assert members(catalog, t(15), t(20)).member_ids == ("security-a",)
    removed = members(catalog, t(15), t(21))
    assert removed.member_ids == () and removed.selected_versions == (removal.version,)
    absent = UniverseCatalog([removal]).members_at("universe-a", "membership-source", t(15), t(20))
    assert absent.member_ids == () and absent.selected_versions == ()


def test_still_member_after_delisting_is_explicitly_unresolved() -> None:
    member = history()
    ended = listing(end=t(10))
    result = joined(UniverseCatalog([member]), ListingCatalog([ended]), t(10), t(20))
    assert result.membership.member_ids == ("security-a",)
    assert result.matches == () and result.unresolved_member_ids == ("security-a",)
    assert result.membership.selected_versions == (member.version,)
    assert result.listing_results[0].selected_versions == (ended.version,)
    historical = joined(UniverseCatalog([member]), ListingCatalog([ended]), t(9), t(20))
    assert historical.matches[0].interval.end_reason == "delisted"


def test_mapping_and_membership_select_independent_availability_at_same_decision() -> None:
    initial = history()
    removal = history("m2", 2, t(21), ())
    old = listing()
    corrected = listing("l2", 2, t(22), symbol="NEW", start=t(10), published=t(18))
    mapping = ListingCatalog([corrected, old])
    with_removal = UniverseCatalog([removal, initial])
    before = joined(with_removal, mapping, t(15), t(20))
    assert before.membership.selected_versions == (initial.version,)
    assert before.matches[0].version is old.version
    assert before.matches[0].interval.symbol == "OLD"
    removed = joined(with_removal, mapping, t(15), t(21))
    assert removed.membership.selected_versions == (removal.version,)
    assert removed.membership.member_ids == () and removed.listing_results == ()
    still_member = UniverseCatalog([initial])
    assert joined(still_member, mapping, t(15), t(21)).matches[0].interval.symbol == "OLD"
    revised = joined(still_member, mapping, t(15), t(22))
    assert revised.matches[0].interval.symbol == "NEW"
    assert revised.matches[0].version is corrected.version
    assert revised.membership.effective_at == revised.listing_results[0].effective_at == t(15)
    assert revised.membership.decision_at == revised.listing_results[0].decision_at == t(22)
    assert old.version.availability.ingested_at == t(31)  # Backfill does not block old knowledge.


def test_removed_listing_interval_does_not_fall_back_or_drop_member() -> None:
    old = listing()
    empty = listing("l2", 2, t(20), empty=True)
    result = joined(UniverseCatalog([history()]), ListingCatalog([old, empty]), t(5), t(20))
    assert result.unresolved_member_ids == ("security-a",) and result.matches == ()
    assert result.listing_results[0].selected_versions == (empty.version,)
    unknown = joined(UniverseCatalog([history()]), ListingCatalog([]), t(5), t(20))
    assert unknown.unresolved_member_ids == ("security-a",)
    assert unknown.listing_results[0].selected_versions == ()


def test_ticker_reuse_never_rebinds_old_member_to_new_security() -> None:
    membership = UniverseCatalog([history(), history(security="security-b")])
    mapping = ListingCatalog([listing(end=t(10)), listing(security="security-b", start=t(10))])
    before = joined(membership, mapping, t(9), t(20))
    after = joined(membership, mapping, t(10), t(20))
    assert before.matches[0].version.key.security_id == "security-a"
    assert before.unresolved_member_ids == ("security-b",)
    assert after.matches[0].version.key.security_id == "security-b"
    assert after.unresolved_member_ids == ("security-a",)
    assert after.membership.member_ids == ("security-a", "security-b")


def test_exact_source_universe_venue_partitions_and_deterministic_order() -> None:
    a = history()
    b = history(security="security-b")
    other_source = history("other-source", 90, intervals=(), source="other-source")
    other_universe = history("other-universe", 100, intervals=(), universe="universe-b")
    catalog = UniverseCatalog([b, other_universe, other_source, a])
    result = members(catalog, t(5), t(20))
    assert result.member_ids == ("security-a", "security-b")
    assert result.selected_versions == (a.version, b.version)
    for universe, source in [("universe-b", "membership-source"), ("universe-a", "other-source")]:
        assert catalog.members_at(universe, source, t(5), t(20)).member_ids == ()
    assert (
        catalog.members_at("Universe-a", "membership-source", t(5), t(20)).selected_versions == ()
    )
    # Neither the wrong listing source nor another venue may supply a fallback.
    other_venue = listing(venue="XNAS")
    wrong = ListingCatalog([listing(source="other-source"), other_venue])
    joined_result = joined(catalog, wrong, t(5), t(20))
    assert joined_result.unresolved_member_ids == ("security-a", "security-b")
    assert joined_result.listing_results[0].selected_versions == (other_venue.version,)
    assert membership_observation_id("a:b") != membership_observation_id("a")


def test_same_symbol_preserves_distinct_stable_members_and_symbol_resolution_fails() -> None:
    catalog = UniverseCatalog([history(), history(security="security-b")])
    mapping = ListingCatalog([listing(), listing(security="security-b")])
    result = joined(catalog, mapping, t(5), t(20))
    assert result.membership.member_ids == ("security-a", "security-b")
    assert tuple(match.version.key.security_id for match in result.matches) == (
        "security-a",
        "security-b",
    )
    assert result.unresolved_member_ids == ()
    with pytest.raises(ValueError, match="ambiguous symbol"):
        mapping.resolve_symbol_at("OLD", "listing-source", "XNYS", t(5), t(20))


@pytest.mark.parametrize(
    "intervals",
    [
        (MembershipInterval(t(1)), MembershipInterval(t(1))),
        (MembershipInterval(t(1), t(10)), MembershipInterval(t(9), t(20))),
        (MembershipInterval(t(1)), MembershipInterval(t(20))),
    ],
)
def test_duplicate_and_overlapping_membership_fail(
    intervals: tuple[MembershipInterval, ...],
) -> None:
    with pytest.raises(ValueError, match="overlapping"):
        history(intervals=intervals)


def test_duplicate_revision_identity_rank_and_contradictory_availability_fail() -> None:
    first = history()
    with pytest.raises(ValueError, match="duplicate version_id"):
        UniverseCatalog([first, first])
    with pytest.raises(ValueError, match="duplicate revision_rank"):
        UniverseCatalog([first, history("another")])
    with pytest.raises(ValueError, match="contradicts rank"):
        UniverseCatalog([history(usable=t(2)), history("m2", 2, t(1))])
    tied = history("m2", 2, t(1), ())
    assert members(UniverseCatalog([first, tied]), t(1), t(1)).selected_versions == (tied.version,)


def test_history_binding_snapshots_and_frozen_results() -> None:
    first = history()
    with pytest.raises(ValueError, match="observation_id"):
        replace(first, universe_id="different")
    with pytest.raises(ValueError, match="observation_id"):
        replace(first, version=replace(first.version, key=ObservationKey("s", "v", "other")))
    raw = [MembershipInterval(t(1))]
    copied = replace(first, intervals=raw)
    raw.clear()
    records = [copied]
    catalog = UniverseCatalog(records)
    records.clear()
    result = members(catalog, t(1), t(1))
    assert result.member_ids == ("security-a",) and len(copied.intervals) == 1
    with pytest.raises(FrozenInstanceError):
        copied.intervals[0].effective_until = t(2)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        result.members = ()


@pytest.mark.parametrize(
    "invalid", ["", b"", bytearray(), memoryview(b""), {}, set(), frozenset(), None, 0]
)
def test_malformed_empty_history_containers_cannot_assert_deletion(invalid: Any) -> None:
    with pytest.raises(ValueError, match="intervals must be a tuple or list"):
        replace(history(), intervals=invalid)


@pytest.mark.parametrize("invalid", ["", b"", bytearray(), memoryview(b""), {}, None, 0])
def test_malformed_catalog_containers_cannot_assert_no_eligible_members(invalid: Any) -> None:
    with pytest.raises(ValueError, match="histories must be an iterable"):
        UniverseCatalog(invalid)


def test_unknown_availability_quarantines_and_cannot_enter_membership() -> None:
    unknown = RawTimestampClaim(None, None, TimestampStatus.UNKNOWN, None, "not established")
    raw = RawAvailability(
        ObservationKey("security-a", "membership-source", membership_observation_id("universe-a")),
        "unknown",
        None,
        unknown,
        unknown,
        t(31),
    )
    quarantine = admit_availability(raw)
    assert isinstance(quarantine, QuarantinedAvailability)
    assert {issue.field for issue in quarantine.reasons} == {"published_at", "source_available_at"}
    for invalid in (raw, quarantine):
        with pytest.raises(ValueError, match="ObservationVersion"):
            replace(history(), version=invalid)
        with pytest.raises(ValueError, match="MembershipHistory"):
            UniverseCatalog([invalid])  # type: ignore[list-item]
    with pytest.raises(ValueError, match="InformationAvailability"):
        replace(history().version, availability=quarantine)


def test_dst_fold_compares_real_instants_and_normalizes_queries() -> None:
    eastern = ZoneInfo("America/New_York")
    start = datetime(2025, 11, 2, 1, 30, tzinfo=eastern, fold=0)  # 05:30Z
    end = datetime(2025, 11, 2, 1, 15, tzinfo=eastern, fold=1)  # 06:15Z
    interval = MembershipInterval(start, end)
    assert interval.effective_from == datetime(2025, 11, 2, 5, 30, tzinfo=UTC)
    assert interval.effective_until == datetime(2025, 11, 2, 6, 15, tzinfo=UTC)
    catalog = UniverseCatalog([history(intervals=(interval,))])
    at_start = members(catalog, start, end)
    assert at_start.member_ids == ("security-a",)
    assert at_start.effective_at.tzinfo is UTC and at_start.decision_at.tzinfo is UTC
    assert members(catalog, end, end).member_ids == ()


@pytest.mark.parametrize(
    "invalid",
    [datetime(2025, 1, 1), datetime(2025, 3, 9, 2, 30, tzinfo=ZoneInfo("America/New_York")), None],
)
def test_invalid_query_and_effective_times_reject_even_with_no_histories(invalid: Any) -> None:
    catalog = UniverseCatalog([])
    for effective, decision in [(invalid, t(20)), (t(1), invalid)]:
        with pytest.raises(ValueError):
            members(catalog, effective, decision)
        with pytest.raises(ValueError):
            joined(catalog, ListingCatalog([]), effective, decision)
    with pytest.raises(ValueError):
        MembershipInterval(invalid)
    if invalid is not None:
        with pytest.raises(ValueError):
            MembershipInterval(t(1), invalid)


@pytest.mark.parametrize(
    "field", ["event_at", "published_at", "source_available_at", "ingested_at"]
)
def test_metadata_cannot_bypass_dst_gap_validation(field: str) -> None:
    first = history()
    gap = datetime(2025, 3, 9, 2, 30, tzinfo=ZoneInfo("America/New_York"))
    invalid = replace(first.version.availability, **{field: gap})
    with pytest.raises(ValueError, match="nonexistent"):
        replace(first, version=replace(first.version, availability=invalid))


def test_invalid_contracts_and_blank_queries_fail() -> None:
    catalog = UniverseCatalog([])
    with pytest.raises(ValueError, match="effective_at must not follow"):
        members(catalog, t(20), t(19))
    for end in (t(1), t(1) - timedelta(seconds=1)):
        with pytest.raises(ValueError, match="must follow"):
            MembershipInterval(t(1), end)
    with pytest.raises(ValueError, match="MembershipInterval"):
        replace(history(), intervals=("raw",))
    for universe, source in [("", "source"), ("universe", " ")]:
        with pytest.raises(ValueError):
            catalog.members_at(universe, source, t(1), t(1))
    for source, venue in [("", "XNYS"), ("listing-source", " ")]:
        with pytest.raises(ValueError):
            catalog.listings_at(
                "universe-a", "membership-source", ListingCatalog([]), source, venue, t(1), t(1)
            )
    with pytest.raises(ValueError, match="ListingCatalog"):
        joined(catalog, None, t(1), t(1))  # type: ignore[arg-type]
