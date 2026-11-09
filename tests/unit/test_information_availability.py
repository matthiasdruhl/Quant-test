"""Independent boundary cases for point-in-time availability."""

from datetime import UTC, datetime, timedelta, timezone

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
