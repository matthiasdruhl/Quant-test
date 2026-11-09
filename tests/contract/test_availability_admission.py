"""Hand-specified raw admission, historical, and operational boundary cases."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from quant_test.data.admission import (
    AcceptedAvailability,
    AvailabilityIssue,
    QuarantinedAvailability,
    RawAvailability,
    RawTimestampClaim,
    TimestampStatus,
    admit_availability,
)
from quant_test.data.versions import ObservationKey, ObservationVersion, VersionCatalog

KEY = ObservationKey("security-1", "vendor-a", "release-2025-01-03")


def hour(value: int) -> datetime:
    return datetime(2025, 1, 3, value, tzinfo=UTC)


def claim(value: datetime | date | None) -> RawTimestampClaim:
    return RawTimestampClaim(
        value, "original vendor timestamp", TimestampStatus.EXACT, "v1-log", None
    )


def raw() -> RawAvailability:
    return RawAvailability(
        key=KEY,
        version_id="v1",
        event_at=None,
        published_at=claim(hour(10)),
        source_available_at=claim(hour(11)),
        ingested_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def observation(accepted: AcceptedAvailability, rank: int) -> ObservationVersion:
    return ObservationVersion(
        key=accepted.raw.key,
        version_id=accepted.raw.version_id,
        revision_rank=rank,
        availability=accepted.availability,
        source_uri="https://vendor.example/version",
        license_id="reference-case",
        content_sha256="a" * 64,
        retracted=False,
    )


def test_unknown_event_backfill_and_operational_gate_are_preserved() -> None:
    envelope = raw()
    result = admit_availability(envelope)
    assert isinstance(result, AcceptedAvailability)
    assert result.raw is envelope
    assert result.raw.published_at.source_text == "original vendor timestamp"
    assert result.availability.event_at is None
    # Public 10:00, provider 11:00, ingestion in 2026: exact equality admits replay.
    assert not result.availability.is_usable_at(hour(10))
    assert result.availability.is_usable_at(hour(11))
    processed = datetime(2026, 1, 1, 1, tzinfo=UTC)
    assert not result.availability.is_available_to_platform_at(hour(12), processed_at=processed)
    assert not result.availability.is_available_to_platform_at(
        envelope.ingested_at, processed_at=processed
    )
    assert result.availability.is_available_to_platform_at(processed, processed_at=processed)
    with pytest.raises(ValueError, match="processed_at must not precede ingested_at"):
        result.availability.is_available_to_platform_at(processed, processed_at=hour(12))
    with pytest.raises(ValueError, match="processed_at must be timezone-aware"):
        result.availability.is_available_to_platform_at(processed, processed_at=None)  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["published_at", "source_available_at"])
@pytest.mark.parametrize(
    ("value", "reason"),
    [
        (None, "missing or unparsed timestamp"),
        (date(2025, 1, 3), "date-only value has no exact release instant"),
        (datetime(2025, 1, 3, 10), "timestamp must be timezone-aware"),
    ],
)
def test_missing_date_only_and_naive_claims_quarantine_without_inference(
    field: str, value: datetime | date | None, reason: str
) -> None:
    envelope = replace(raw(), **{field: claim(value)})
    result = admit_availability(envelope)
    assert isinstance(result, QuarantinedAvailability)
    assert result.raw is envelope
    assert result.reasons == (AvailabilityIssue(field, reason),)
    assert getattr(result.raw, field).parsed_value is value
    assert not hasattr(result, "availability")


@pytest.mark.parametrize("field", ["published_at", "source_available_at"])
@pytest.mark.parametrize(
    "status", [TimestampStatus.UNKNOWN, TimestampStatus.APPROXIMATE, TimestampStatus.UNVERIFIED]
)
def test_uncertain_aware_claim_is_not_proven_by_a_nonblank_evidence_string(
    field: str, status: TimestampStatus
) -> None:
    uncertain = replace(
        claim(hour(10)),
        status=status,
        evidence_reference="vendor typical release time",
        uncertainty_reason="estimated from the provider's usual schedule",
    )
    envelope = replace(raw(), **{field: uncertain})
    result = admit_availability(envelope)
    assert isinstance(result, QuarantinedAvailability)
    assert result.raw is envelope
    assert result.reasons == (
        AvailabilityIssue(field, f"status is {status.value}, not exact"),
        AvailabilityIssue(field, "timestamp uncertainty is declared"),
    )
    assert getattr(result.raw, field).uncertainty_reason == uncertain.uncertainty_reason


@pytest.mark.parametrize("field", ["published_at", "source_available_at"])
def test_exact_label_cannot_override_a_declared_uncertainty(field: str) -> None:
    uncertain = replace(claim(hour(10)), uncertainty_reason="release instant has not been verified")
    result = admit_availability(replace(raw(), **{field: uncertain}))
    assert isinstance(result, QuarantinedAvailability)
    assert result.reasons == (AvailabilityIssue(field, "timestamp uncertainty is declared"),)


@pytest.mark.parametrize("field", ["published_at", "source_available_at"])
@pytest.mark.parametrize("evidence", [None, "", "  \t"])
def test_missing_evidence_quarantines_each_required_field(field: str, evidence: str | None) -> None:
    result = admit_availability(
        replace(raw(), **{field: replace(claim(hour(10)), evidence_reference=evidence)})
    )
    assert isinstance(result, QuarantinedAvailability)
    assert result.reasons == (AvailabilityIssue(field, "missing nonblank evidence reference"),)


def test_both_missing_claims_retain_all_field_specific_reasons_and_source_text() -> None:
    missing = RawTimestampClaim(
        None, "not supplied", TimestampStatus.UNKNOWN, None, "absent in log"
    )
    envelope = replace(raw(), published_at=missing, source_available_at=missing)
    result = admit_availability(envelope)
    assert isinstance(result, QuarantinedAvailability)
    expected_reasons = (
        "status is unknown, not exact",
        "missing or unparsed timestamp",
        "missing nonblank evidence reference",
        "timestamp uncertainty is declared",
    )
    assert result.reasons == tuple(
        AvailabilityIssue(field, reason)
        for field in ("published_at", "source_available_at")
        for reason in expected_reasons
    )
    assert result.raw.published_at is missing
    assert result.raw.source_available_at.source_text == "not supplied"


def test_missing_uncertainty_reason_remains_quarantined() -> None:
    result = admit_availability(
        replace(raw(), published_at=replace(claim(hour(10)), status=TimestampStatus.APPROXIMATE))
    )
    assert isinstance(result, QuarantinedAvailability)
    assert (
        AvailabilityIssue("published_at", "missing nonblank uncertainty reason") in result.reasons
    )


@pytest.mark.parametrize("field", ["published_at", "source_available_at"])
def test_exact_claim_may_omit_source_text_when_evidence_is_supplied(field: str) -> None:
    original = replace(claim(hour(10)), source_text=None)
    result = admit_availability(replace(raw(), **{field: original}))
    assert isinstance(result, AcceptedAvailability)
    assert getattr(result.raw, field).source_text is None
    assert getattr(result.availability, field) == hour(10)


def test_future_event_does_not_delay_an_earlier_announcement() -> None:
    result = admit_availability(replace(raw(), event_at=hour(20)))
    assert isinstance(result, AcceptedAvailability)
    assert result.availability.event_at == hour(20)
    assert result.availability.is_usable_at(hour(11))


@pytest.mark.parametrize("field", ["event_at", "ingested_at"])
def test_naive_envelope_times_quarantine(field: str) -> None:
    result = admit_availability(replace(raw(), **{field: datetime(2025, 1, 3, 10)}))
    assert isinstance(result, QuarantinedAvailability)
    assert result.reasons == (AvailabilityIssue(field, "timestamp must be timezone-aware"),)


@pytest.mark.parametrize(
    "field", ["published_at", "source_available_at", "event_at", "ingested_at"]
)
@pytest.mark.parametrize("fold", [0, 1])
def test_spring_dst_gap_quarantines_without_inventing_a_utc_instant(field: str, fold: int) -> None:
    # New York skipped directly from 01:59:59 EST to 03:00:00 EDT on this date.
    # Neither fold marker makes the nonexistent 02:30 a valid civil time.
    nonexistent = datetime(2025, 3, 9, 2, 30, tzinfo=ZoneInfo("America/New_York"), fold=fold)
    value = claim(nonexistent) if field in ("published_at", "source_available_at") else nonexistent
    envelope = replace(raw(), **{field: value})
    result = admit_availability(envelope)
    assert isinstance(result, QuarantinedAvailability)
    assert result.raw is envelope
    assert result.reasons == (AvailabilityIssue(field, "timestamp is a nonexistent local time"),)
    assert not hasattr(result, "availability")


@pytest.mark.parametrize(
    "field", ["published_at", "source_available_at", "event_at", "ingested_at"]
)
@pytest.mark.parametrize(("fold", "utc_hour"), [(0, 5), (1, 6)])
def test_both_real_fall_dst_folds_remain_valid_in_every_timestamp_field(
    field: str, fold: int, utc_hour: int
) -> None:
    # 01:30 EDT is 05:30Z; the second 01:30 EST is 06:30Z.
    original = datetime(2025, 11, 2, 1, 30, tzinfo=ZoneInfo("America/New_York"), fold=fold)
    value = claim(original) if field in ("published_at", "source_available_at") else original
    result = admit_availability(replace(raw(), **{field: value}))
    assert isinstance(result, AcceptedAvailability)
    assert getattr(result.availability, field) == datetime(2025, 11, 2, utc_hour, 30, tzinfo=UTC)


def test_offset_claims_normalize_validated_times_without_rewriting_raw_claims() -> None:
    eastern = timezone(timedelta(hours=-5))
    original = datetime(2025, 1, 3, 6, tzinfo=eastern)  # 11:00 UTC
    envelope = replace(raw(), published_at=claim(original), source_available_at=claim(hour(10)))
    result = admit_availability(envelope)
    assert isinstance(result, AcceptedAvailability)
    assert result.raw.published_at.parsed_value is original
    assert result.availability.published_at == hour(11)
    assert result.availability.published_at.tzinfo is UTC
    assert not result.availability.is_usable_at(hour(10))
    assert result.availability.is_usable_at(hour(11))


def test_dst_fold_uses_the_independent_0615_utc_reference_cutoff() -> None:
    eastern = ZoneInfo("America/New_York")
    envelope = replace(
        raw(),
        published_at=claim(datetime(2025, 11, 2, 1, 30, tzinfo=eastern, fold=0)),  # 05:30Z
        source_available_at=claim(datetime(2025, 11, 2, 1, 15, tzinfo=eastern, fold=1)),  # 06:15Z
    )
    result = admit_availability(envelope)
    assert isinstance(result, AcceptedAvailability)
    assert result.availability.first_usable_at == datetime(2025, 11, 2, 6, 15, tzinfo=UTC)
    assert not result.availability.is_usable_at(datetime(2025, 11, 2, 6, tzinfo=UTC))
    assert result.availability.is_usable_at(datetime(2025, 11, 2, 6, 15, tzinfo=UTC))


def test_quarantined_amendment_cannot_inherit_previous_version_evidence() -> None:
    first = admit_availability(raw())
    assert isinstance(first, AcceptedAvailability)
    amendment = replace(
        raw(),
        version_id="v2",
        published_at=replace(claim(hour(12)), evidence_reference=None),
        source_available_at=replace(claim(hour(13)), evidence_reference=None),
    )
    rejected = admit_availability(amendment)
    assert isinstance(rejected, QuarantinedAvailability)
    assert {issue.field for issue in rejected.reasons} == {"published_at", "source_available_at"}
    catalog = VersionCatalog([observation(first, 1)])
    selected = catalog.latest_usable_at(KEY, hour(14))
    assert selected is not None and selected.version_id == "v1"
    # Neither a raw envelope nor either admission result is a validated version.
    for invalid in (amendment, rejected, first):
        with pytest.raises(ValueError, match="versions must contain ObservationVersion"):
            VersionCatalog([invalid])  # type: ignore[list-item]


def test_admitted_versions_keep_existing_catalog_revision_boundaries() -> None:
    first = admit_availability(raw())
    second = admit_availability(
        replace(
            raw(),
            version_id="v2",
            published_at=replace(claim(hour(12)), evidence_reference="v2-public-log"),
            source_available_at=replace(claim(hour(13)), evidence_reference="v2-provider-log"),
        )
    )
    assert isinstance(first, AcceptedAvailability)
    assert isinstance(second, AcceptedAvailability)
    catalog = VersionCatalog([observation(second, 2), observation(first, 1)])
    for cutoff, expected in [
        (hour(10), None),
        (hour(11), "v1"),
        (hour(12), "v1"),
        (hour(13), "v2"),
    ]:
        selected = catalog.latest_usable_at(KEY, cutoff)
        assert (None if selected is None else selected.version_id) == expected


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("parsed_value", "2025-01-03"),
        ("parsed_value", 123),
        ("status", "exact"),
        ("source_text", 123),
        ("evidence_reference", []),
        ("uncertainty_reason", False),
    ],
)
def test_invalid_claim_api_types_raise_value_error(field: str, invalid: Any) -> None:
    with pytest.raises(ValueError, match=field):
        replace(claim(hour(10)), **{field: invalid})


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("key", "ticker"),
        ("version_id", " "),
        ("version_id", 1),
        ("published_at", None),
        ("source_available_at", hour(11)),
        ("event_at", date(2025, 1, 3)),
        ("ingested_at", None),
    ],
)
def test_invalid_envelope_api_types_raise_value_error(field: str, invalid: Any) -> None:
    with pytest.raises(ValueError, match=field):
        replace(raw(), **{field: invalid})


def test_results_cannot_be_constructed_with_the_opposite_admission_state() -> None:
    with pytest.raises(ValueError, match="requires quarantine"):
        AcceptedAvailability(replace(raw(), published_at=claim(None)))
    with pytest.raises(ValueError, match="satisfies admission"):
        QuarantinedAvailability(raw())
    for constructor in (admit_availability, AcceptedAvailability, QuarantinedAvailability):
        with pytest.raises(ValueError, match="raw must be a RawAvailability"):
            constructor(None)  # type: ignore[arg-type]


def test_claim_envelope_results_and_reasons_are_immutable() -> None:
    envelope = raw()
    accepted = admit_availability(envelope)
    rejected = admit_availability(replace(envelope, published_at=claim(None)))
    assert isinstance(rejected, QuarantinedAvailability)
    objects = [
        (envelope.published_at, "status", TimestampStatus.APPROXIMATE),
        (envelope, "version_id", "v2"),
        (accepted, "raw", envelope),
        (rejected, "raw", envelope),
        (rejected.reasons[0], "reason", "changed"),
    ]
    for value, field, replacement in objects:
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, replacement)
