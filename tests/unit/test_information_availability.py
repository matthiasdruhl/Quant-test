"""Independent boundary cases for point-in-time availability."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from quant_test.core.time import InformationAvailability


def at_hour(hour: int) -> datetime:
    return datetime(2025, 1, 3, hour, tzinfo=UTC)


def information() -> InformationAvailability:
    return InformationAvailability(
        event_at=at_hour(10),
        published_at=at_hour(12),
        source_available_at=at_hour(14),
        ingested_at=at_hour(18),
    )


@pytest.mark.parametrize(
    ("decision_hour", "expected"),
    [(11, False), (12, False), (13, False), (14, True), (15, True)],
)
def test_usable_only_after_both_public_and_source_release(
    decision_hour: int, expected: bool
) -> None:
    assert information().is_usable_at(at_hour(decision_hour)) is expected


def test_historical_backfill_ingestion_does_not_shift_source_availability() -> None:
    assert information().first_usable_at == at_hour(14)
    assert information().is_usable_at(at_hour(15))


def test_offsets_are_compared_by_instant_not_wall_clock() -> None:
    eastern = timezone(timedelta(hours=-5))
    decision = datetime(2025, 1, 3, 9, tzinfo=eastern)
    assert information().is_usable_at(decision)


@pytest.mark.parametrize(
    "field",
    ["event_at", "published_at", "source_available_at", "ingested_at"],
)
def test_naive_record_timestamps_are_rejected(field: str) -> None:
    kwargs = {
        "event_at": at_hour(10),
        "published_at": at_hour(12),
        "source_available_at": at_hour(14),
        "ingested_at": at_hour(18),
    }
    kwargs[field] = datetime(2025, 1, 3, 10)
    with pytest.raises(ValueError, match="timezone-aware"):
        InformationAvailability(**kwargs)


def test_naive_decision_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="decision_at must be timezone-aware"):
        information().is_usable_at(datetime(2025, 1, 3, 15))


def test_future_event_can_be_announced_earlier() -> None:
    record = InformationAvailability(
        event_at=at_hour(20),
        published_at=at_hour(9),
        source_available_at=at_hour(10),
        ingested_at=at_hour(22),
    )
    assert record.is_usable_at(at_hour(11))


def test_unknown_event_time_does_not_invent_or_block_known_availability() -> None:
    record = InformationAvailability(
        event_at=None,
        published_at=at_hour(12),
        source_available_at=at_hour(14),
        ingested_at=at_hour(18),
    )
    assert record.event_at is None
    assert not record.is_usable_at(at_hour(13))
    assert record.is_usable_at(at_hour(14))


@pytest.mark.parametrize("field", ["published_at", "source_available_at", "ingested_at"])
@pytest.mark.parametrize("invalid", [None, "2025-01-03T12:00:00Z"])
def test_missing_or_unparsed_required_timestamps_fail_closed(field: str, invalid: Any) -> None:
    values: dict[str, Any] = {
        "event_at": at_hour(10),
        "published_at": at_hour(12),
        "source_available_at": at_hour(14),
        "ingested_at": at_hour(18),
    }
    values[field] = invalid
    with pytest.raises(ValueError, match=f"{field} must be timezone-aware"):
        InformationAvailability(**values)


def test_publication_can_be_later_than_provider_availability() -> None:
    record = InformationAvailability(at_hour(10), at_hour(15), at_hour(12), at_hour(18))
    assert not record.is_usable_at(at_hour(14))
    assert record.is_usable_at(at_hour(15))


@pytest.mark.parametrize(("decision_hour", "expected"), [(15, False), (18, False), (19, True)])
def test_platform_availability_waits_for_local_processing(
    decision_hour: int, expected: bool
) -> None:
    record = information()
    assert record.is_usable_at(at_hour(15))
    assert (
        record.is_available_to_platform_at(at_hour(decision_hour), processed_at=at_hour(19))
        is expected
    )


def test_platform_availability_still_waits_for_public_release() -> None:
    record = InformationAvailability(at_hour(10), at_hour(20), at_hour(12), at_hour(18))
    assert not record.is_available_to_platform_at(at_hour(19), processed_at=at_hour(19))
    assert record.is_available_to_platform_at(at_hour(20), processed_at=at_hour(19))


def test_platform_processing_cannot_precede_ingestion() -> None:
    with pytest.raises(ValueError, match="processed_at must not precede ingested_at"):
        information().is_available_to_platform_at(at_hour(20), processed_at=at_hour(17))


@pytest.mark.parametrize("field", ["decision_at", "processed_at"])
@pytest.mark.parametrize("invalid", [None, datetime(2025, 1, 3, 20)])
def test_platform_gate_rejects_missing_or_naive_timestamps(field: str, invalid: Any) -> None:
    values: dict[str, Any] = {"decision_at": at_hour(20), "processed_at": at_hour(19)}
    values[field] = invalid
    with pytest.raises(ValueError, match=f"{field} must be timezone-aware"):
        information().is_available_to_platform_at(**values)


def test_platform_availability_compares_instants_across_offsets() -> None:
    eastern = timezone(timedelta(hours=-5))
    assert information().is_available_to_platform_at(
        at_hour(19), processed_at=datetime(2025, 1, 3, 14, tzinfo=eastern)
    )


def test_historical_availability_orders_repeated_dst_hour_by_utc_instant() -> None:
    eastern = ZoneInfo("America/New_York")
    # 01:30 EDT = 05:30 UTC, then 01:15 EST = 06:15 UTC on the same date.
    record = InformationAvailability(
        event_at=None,
        published_at=datetime(2025, 11, 2, 1, 30, tzinfo=eastern, fold=0),
        source_available_at=datetime(2025, 11, 2, 1, 15, tzinfo=eastern, fold=1),
        ingested_at=datetime(2025, 11, 2, 7, tzinfo=UTC),
    )
    assert record.first_usable_at == datetime(2025, 11, 2, 6, 15, tzinfo=UTC)
    assert not record.is_usable_at(datetime(2025, 11, 2, 1, 45, tzinfo=eastern, fold=0))
    assert record.is_usable_at(datetime(2025, 11, 2, 1, 15, tzinfo=eastern, fold=1))


def test_platform_processing_orders_repeated_dst_hour_by_utc_instant() -> None:
    eastern = ZoneInfo("America/New_York")
    record = InformationAvailability(
        event_at=None,
        published_at=datetime(2025, 11, 2, 4, tzinfo=UTC),
        source_available_at=datetime(2025, 11, 2, 5, tzinfo=UTC),
        ingested_at=datetime(2025, 11, 2, 1, 30, tzinfo=eastern, fold=0),
    )
    processed = datetime(2025, 11, 2, 1, 15, tzinfo=eastern, fold=1)
    assert not record.is_available_to_platform_at(
        datetime(2025, 11, 2, 1, 45, tzinfo=eastern, fold=0), processed_at=processed
    )
    assert record.is_available_to_platform_at(
        datetime(2025, 11, 2, 6, 15, tzinfo=UTC), processed_at=processed
    )
    # Processing earlier in real time must reject even if its wall clock is later.
    later_ingest = InformationAvailability(
        event_at=None,
        published_at=record.published_at,
        source_available_at=record.source_available_at,
        ingested_at=processed,
    )
    with pytest.raises(ValueError, match="processed_at must not precede ingested_at"):
        later_ingest.is_available_to_platform_at(
            datetime(2025, 11, 2, 7, tzinfo=UTC),
            processed_at=record.ingested_at,
        )
