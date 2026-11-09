"""Hand-specified effective/knowledge-time listing references, not provider data."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from quant_test.core.time import InformationAvailability
from quant_test.data.listings import (
    LISTING_HISTORY_OBSERVATION_ID,
    ListingCatalog,
    ListingHistory,
    ListingInterval,
)
from quant_test.data.versions import ObservationKey, ObservationVersion


def instant(month: int, day: int = 1, hour: int = 0) -> datetime:
    return datetime(2025, month, day, hour, tzinfo=UTC)


INITIAL_START = instant(1)


def interval(
    symbol: str = "OLD",
    start: datetime = INITIAL_START,
    end: datetime | None = None,
    reason: str | None = None,
    venue: str = "XNYS",
) -> ListingInterval:
    return ListingInterval("issuer-a", symbol, venue, "USD", start, end, reason)


def history(
    version_id: str,
    rank: int,
    usable: datetime,
    intervals: tuple[ListingInterval, ...],
    *,
    security: str = "security-a",
    source: str = "source-a",
    published: datetime | None = None,
) -> ListingHistory:
    return ListingHistory(
        ObservationVersion(
            ObservationKey(security, source, LISTING_HISTORY_OBSERVATION_ID),
            version_id,
            rank,
            InformationAvailability(
                None,
                usable if published is None else published,
                usable,
                datetime(2026, 1, 1, tzinfo=UTC),
            ),
            f"https://source.example/{version_id}",
            "reference-fixture-license",
            "a" * 64,
            False,
        ),
        intervals,
    )


def test_initial_listing_boundary_and_absence_retain_selected_provenance() -> None:
    first = history("initial", 1, instant(1), (interval(start=instant(1, 3)),))
    catalog = ListingCatalog([first])
    # Listed from Jan 3; announcement was usable Jan 1; ingest in 2026 is irrelevant.
    before = catalog.listing_at("security-a", "source-a", "XNYS", instant(1, 2), instant(1, 4))
    assert before.match is None
    assert before.selected_versions == (first.version,)
    at_start = catalog.listing_at("security-a", "source-a", "XNYS", instant(1, 3), instant(1, 3))
    assert at_start.match is not None
    assert at_start.match.interval.symbol == "OLD"
    assert at_start.match.version is first.version
    assert at_start.effective_at == instant(1, 3)
    assert at_start.decision_at == instant(1, 3)
    unknown = catalog.listing_at("missing", "source-a", "XNYS", instant(1), instant(1))
    assert unknown.match is None and unknown.selected_versions == ()


@pytest.mark.parametrize("reverse", [False, True])
def test_future_announced_rename_uses_effective_boundary_and_historical_revision(
    reverse: bool,
) -> None:
    first = history("initial", 1, instant(1), (interval(),))
    rename = history(
        "rename",
        2,
        instant(2),
        (
            interval(end=instant(3), reason="symbol_changed"),
            interval("NEW", instant(3)),
        ),
    )
    records = [first, rename]
    catalog = ListingCatalog(reversed(records) if reverse else records)
    # February knowledge includes the announced March rename but OLD is effective.
    feb = catalog.listing_at("security-a", "source-a", "XNYS", instant(2, 2), instant(2, 2))
    assert feb.match is not None
    assert feb.match.version.version_id == "rename" and feb.match.interval.symbol == "OLD"
    march = catalog.listing_at("security-a", "source-a", "XNYS", instant(3), instant(3))
    assert march.match is not None and march.match.interval.symbol == "NEW"
    assert (
        catalog.resolve_symbol_at("OLD", "source-a", "XNYS", instant(3), instant(3)).match is None
    )
    january = catalog.listing_at("security-a", "source-a", "XNYS", instant(1), instant(1))
    assert january.match is not None and january.match.version.version_id == "initial"
    with pytest.raises(ValueError, match="effective_at must not follow"):
        catalog.listing_at("security-a", "source-a", "XNYS", instant(3), instant(2))


def test_delisting_survives_historically_and_late_correction_does_not_leak() -> None:
    # v3 says ended Apr 1 14:00. Apr 10 12:00 correction v4 says Apr 1 16:00.
    ended = history("v3", 3, instant(3), (interval(end=instant(4, 1, 14), reason="delisted"),))
    correction = history(
        "v4", 4, instant(4, 10, 12), (interval(end=instant(4, 1, 16), reason="delisted"),)
    )
    catalog = ListingCatalog([correction, ended])
    earlier = catalog.listing_at("security-a", "source-a", "XNYS", instant(4, 1, 15), instant(4, 5))
    assert earlier.match is None and earlier.selected_versions == (ended.version,)
    corrected = catalog.listing_at(
        "security-a", "source-a", "XNYS", instant(4, 1, 15), instant(4, 10, 12)
    )
    assert corrected.match is not None and corrected.match.version is correction.version
    boundary = catalog.listing_at("security-a", "source-a", "XNYS", instant(4, 1, 16), instant(5))
    assert boundary.match is None and boundary.selected_versions == (correction.version,)
    historical = catalog.listing_at("security-a", "source-a", "XNYS", instant(2), instant(5))
    assert historical.match is not None
    assert historical.match.interval.end_reason == "delisted"


def test_complete_replacement_removes_interval_without_fallback() -> None:
    old = history("old", 1, instant(1), (interval(),))
    empty = history("empty", 2, instant(2), ())
    catalog = ListingCatalog([old, empty])
    for result in (
        catalog.listing_at("security-a", "source-a", "XNYS", instant(1), instant(2)),
        catalog.resolve_symbol_at("OLD", "source-a", "XNYS", instant(1), instant(2)),
    ):
        assert result.match is None and result.selected_versions == (empty.version,)
    assert (
        catalog.resolve_symbol_at("OLD", "source-a", "XNYS", instant(1), instant(1)).match
        is not None
    )


def test_ticker_reuse_resolves_to_distinct_stable_security_ids() -> None:
    catalog = ListingCatalog(
        [
            history("a", 1, instant(1), (interval(end=instant(3), reason="delisted"),)),
            history("b", 1, instant(2), (interval(start=instant(3)),), security="security-b"),
        ]
    )
    before = catalog.resolve_symbol_at("OLD", "source-a", "XNYS", instant(2), instant(4))
    after = catalog.resolve_symbol_at("OLD", "source-a", "XNYS", instant(3), instant(4))
    assert before.match is not None and before.match.version.key.security_id == "security-a"
    assert after.match is not None and after.match.version.key.security_id == "security-b"


def test_ambiguity_checks_only_selected_eligible_revisions() -> None:
    catalog = ListingCatalog(
        [
            history("a", 1, instant(1), (interval(),)),
            history("b1", 1, instant(1), (interval("OTHER"),), security="security-b"),
            history("b2", 2, instant(3), (interval(),), security="security-b"),
        ]
    )
    before = catalog.resolve_symbol_at("OLD", "source-a", "XNYS", instant(2), instant(2))
    assert before.match is not None and before.match.version.key.security_id == "security-a"
    with pytest.raises(ValueError, match="ambiguous symbol"):
        catalog.resolve_symbol_at("OLD", "source-a", "XNYS", instant(2), instant(3))


def test_exact_source_venue_symbol_partition_and_rank_tie() -> None:
    catalog = ListingCatalog(
        [
            history("a-low", 1, instant(1), (interval("lower"),)),
            history("a-high", 2, instant(1), (interval("A.B"), interval("OTHER", venue="XNAS"))),
            history("b", 80, instant(1), (interval("A-B"),), source="source-b"),
        ]
    )
    selected = catalog.resolve_symbol_at("A.B", "source-a", "XNYS", instant(1), instant(1))
    assert selected.match is not None and selected.match.version.version_id == "a-high"
    for symbol, source, venue in [
        ("a.b", "source-a", "XNYS"),
        ("A-B", "source-a", "XNYS"),
        ("A.B", "source-b", "XNYS"),
        ("A.B", "source-a", "XNAS"),
        ("A.B", "source-a", "xnys"),
    ]:
        assert (
            catalog.resolve_symbol_at(symbol, source, venue, instant(1), instant(1)).match is None
        )
    other = catalog.resolve_symbol_at("A-B", "source-b", "XNYS", instant(1), instant(1))
    assert other.match is not None and other.match.version.version_id == "b"


@pytest.mark.parametrize(
    "intervals",
    [
        (interval(), interval("NEW", instant(2))),
        (interval(end=instant(3), reason="changed"), interval("NEW", instant(2))),
        (interval(), interval()),
    ],
)
def test_overlaps_for_same_security_and_venue_reject(
    intervals: tuple[ListingInterval, ...],
) -> None:
    with pytest.raises(ValueError, match="overlapping"):
        history("bad", 1, instant(1), intervals)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("issuer_id", ""),
        ("symbol", " "),
        ("venue", None),
        ("currency", ""),
        ("effective_from", datetime(2025, 1, 1)),
        ("effective_from", "2025-01-01"),
        ("effective_until", instant(1)),
        ("effective_until", instant(1) - timedelta(seconds=1)),
        ("end_reason", "delisted"),
    ],
)
def test_invalid_interval_contract_rejects(field: str, invalid: Any) -> None:
    with pytest.raises(ValueError):
        replace(interval(), **{field: invalid})


@pytest.mark.parametrize("reason", [None, "", " ", 4])
def test_closed_intervals_require_explicit_end_reason(reason: Any) -> None:
    with pytest.raises(ValueError, match="end_reason"):
        interval(end=instant(2), reason=reason)


def test_history_binding_order_and_immutable_payload() -> None:
    first = history("v1", 1, instant(1), (interval(),))
    with pytest.raises(ValueError, match="observation_id"):
        replace(first, version=replace(first.version, key=ObservationKey("s", "v", "other")))
    with pytest.raises(ValueError, match="duplicate version_id"):
        ListingCatalog([first, first])
    with pytest.raises(ValueError, match="duplicate revision_rank"):
        ListingCatalog(
            [first, replace(first, version=replace(first.version, version_id="different"))]
        )
    with pytest.raises(ValueError, match="contradicts rank"):
        ListingCatalog([first, history("v2", 2, datetime(2024, 1, 1, tzinfo=UTC), ())])
    with pytest.raises(FrozenInstanceError):
        first.intervals[0].symbol = "mutated"  # type: ignore[misc]
    raw = [interval()]
    copied = ListingHistory(first.version, raw)  # type: ignore[arg-type]
    raw.clear()
    assert len(copied.intervals) == 1


@pytest.mark.parametrize("invalid", ["", b"", {}, set(), frozenset(), None, 0])
def test_invalid_empty_containers_cannot_assert_complete_history_deletion(invalid: Any) -> None:
    first = history("v1", 1, instant(1), ())
    with pytest.raises(ValueError, match="intervals must be a tuple or list"):
        replace(first, intervals=invalid)


@pytest.mark.parametrize("invalid", ["", b"", bytearray(), {}, None, 0])
def test_invalid_catalog_containers_cannot_silently_assert_no_eligible_history(
    invalid: Any,
) -> None:
    with pytest.raises(ValueError, match="histories must be an iterable of ListingHistory"):
        ListingCatalog(invalid)


def test_publication_and_provider_must_both_be_usable() -> None:
    delayed = history("delayed", 1, instant(1, 2), (interval(),), published=instant(1, 3))
    catalog = ListingCatalog([delayed])
    assert (
        catalog.listing_at(
            "security-a", "source-a", "XNYS", instant(1), instant(1, 2)
        ).selected_versions
        == ()
    )
    assert catalog.listing_at(
        "security-a", "source-a", "XNYS", instant(1), instant(1, 3)
    ).selected_versions == (delayed.version,)


def test_dst_folds_and_offsets_compare_by_instant_and_return_utc() -> None:
    eastern = ZoneInfo("America/New_York")
    start = datetime(2025, 11, 2, 1, 30, tzinfo=eastern, fold=0)  # 05:30Z
    end = datetime(2025, 11, 2, 1, 15, tzinfo=eastern, fold=1)  # 06:15Z
    listing = interval(start=start, end=end, reason="delisted")
    assert listing.effective_from == datetime(2025, 11, 2, 5, 30, tzinfo=UTC)
    assert listing.effective_until == datetime(2025, 11, 2, 6, 15, tzinfo=UTC)
    catalog = ListingCatalog([history("fold", 1, instant(1), (listing,))])
    for effective in [start, datetime(2025, 11, 2, 1, 0, tzinfo=timezone(timedelta(hours=-5)))]:
        result = catalog.listing_at("security-a", "source-a", "XNYS", effective, end)
        assert result.match is not None
        assert result.effective_at.tzinfo is UTC and result.decision_at.tzinfo is UTC
    assert catalog.listing_at("security-a", "source-a", "XNYS", end, end).match is None


@pytest.mark.parametrize(
    "invalid",
    [
        datetime(2025, 1, 1),
        datetime(2025, 3, 9, 2, 30, tzinfo=ZoneInfo("America/New_York")),
    ],
)
def test_naive_and_nonexistent_times_rejected_on_empty_queries_and_intervals(
    invalid: datetime,
) -> None:
    catalog = ListingCatalog([])
    for method, identity in [
        (catalog.listing_at, "security-a"),
        (catalog.resolve_symbol_at, "OLD"),
    ]:
        with pytest.raises(ValueError):
            method(identity, "source-a", "XNYS", invalid, instant(12))
        with pytest.raises(ValueError):
            method(identity, "source-a", "XNYS", instant(1), invalid)
    with pytest.raises(ValueError):
        interval(start=invalid)
    with pytest.raises(ValueError):
        interval(end=invalid, reason="delisted")


@pytest.mark.parametrize(
    "field", ["event_at", "published_at", "source_available_at", "ingested_at"]
)
def test_direct_metadata_cannot_bypass_real_instant_validation(field: str) -> None:
    first = history("v1", 1, instant(1), ())
    gap = datetime(2025, 3, 9, 2, 30, tzinfo=ZoneInfo("America/New_York"))
    availability = replace(first.version.availability, **{field: gap})
    with pytest.raises(ValueError, match="nonexistent"):
        replace(first, version=replace(first.version, availability=availability))


def test_unvalidated_members_and_blank_queries_fail() -> None:
    with pytest.raises(ValueError, match="ListingHistory"):
        ListingCatalog(["raw"])  # type: ignore[list-item]
    first = history("v1", 1, instant(1), ())
    with pytest.raises(ValueError, match="ListingInterval"):
        replace(first, intervals=("raw",))
    for identity, source, venue in [("", "s", "v"), ("x", "", "v"), ("x", "s", "")]:
        for method in [ListingCatalog([]).listing_at, ListingCatalog([]).resolve_symbol_at]:
            with pytest.raises(ValueError):
                method(identity, source, venue, instant(1), instant(1))
