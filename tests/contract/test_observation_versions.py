"""Hand-specified as-of revision boundaries and adversarial provenance cases."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from quant_test.core.time import InformationAvailability
from quant_test.data.versions import ObservationKey, ObservationVersion, VersionCatalog

KEY = ObservationKey("security-1", "vendor-a", "close-2025-01-03")
DIGEST = "a" * 64


def hour(value: int) -> datetime:
    return datetime(2025, 1, 3, value, tzinfo=UTC)


def version(
    version_id: str,
    rank: int,
    published_at: datetime,
    source_available_at: datetime,
    *,
    key: ObservationKey = KEY,
    event_at: datetime | None = None,
) -> ObservationVersion:
    return ObservationVersion(
        key=key,
        version_id=version_id,
        revision_rank=rank,
        availability=InformationAvailability(
            event_at=event_at,
            published_at=published_at,
            source_available_at=source_available_at,
            ingested_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        source_uri="https://vendor.example/record",
        license_id="licensed-fixture",
        content_sha256=DIGEST,
        retracted=False,
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_as_of_selection_uses_public_and_provider_boundaries_not_backfill(reverse: bool) -> None:
    # Independent reference: v1 usable at 11:00, v2 at 13:00, despite 2026 ingestion.
    records = [version("v1", 1, hour(10), hour(11)), version("v2", 2, hour(12), hour(13))]
    catalog = VersionCatalog(reversed(records) if reverse else records)
    expected = [(hour(10), None), (hour(11), "v1"), (hour(12), "v1"), (hour(13), "v2")]
    for cutoff, version_id in expected:
        selected = catalog.latest_usable_at(KEY, cutoff)
        assert (None if selected is None else selected.version_id) == version_id


def test_key_partitions_security_source_and_observation() -> None:
    other_security = ObservationKey("security-2", "vendor-a", KEY.observation_id)
    other_source = ObservationKey(KEY.security_id, "vendor-b", KEY.observation_id)
    other_observation = ObservationKey(KEY.security_id, KEY.source_id, "close-2025-01-04")
    catalog = VersionCatalog(
        [
            version("a", 1, hour(10), hour(11)),
            version("b", 1, hour(10), hour(12), key=other_security),
            version("c", 1, hour(10), hour(13), key=other_source),
            version("d", 1, hour(10), hour(14), key=other_observation),
        ]
    )
    assert catalog.latest_usable_at(KEY, hour(12)).version_id == "a"  # type: ignore[union-attr]
    assert catalog.latest_usable_at(other_security, hour(12)).version_id == "b"  # type: ignore[union-attr]
    assert catalog.latest_usable_at(other_source, hour(12)) is None
    assert catalog.latest_usable_at(other_observation, hour(12)) is None


def test_unknown_event_and_future_event_do_not_replace_release_evidence() -> None:
    catalog = VersionCatalog([version("announced", 1, hour(10), hour(11), event_at=hour(18))])
    assert catalog.latest_usable_at(KEY, hour(11)) is not None
    assert version("undated", 1, hour(10), hour(11)).availability.event_at is None


@pytest.mark.parametrize("field", ["published_at", "source_available_at"])
@pytest.mark.parametrize("invalid", [None, datetime(2025, 1, 3, 10), "estimated 2025-01-03"])
def test_unknown_or_unproven_availability_cannot_enter_catalog(field: str, invalid: Any) -> None:
    times: dict[str, Any] = {
        "event_at": None,
        "published_at": hour(10),
        "source_available_at": hour(11),
        "ingested_at": hour(18),
    }
    times[field] = invalid
    with pytest.raises(ValueError, match=f"{field} must be timezone-aware"):
        InformationAvailability(**times)


def test_duplicate_version_identity_or_rank_is_rejected() -> None:
    first = version("v1", 1, hour(10), hour(11))
    with pytest.raises(ValueError, match="duplicate version_id"):
        VersionCatalog([first, version("v1", 2, hour(12), hour(13))])
    with pytest.raises(ValueError, match="duplicate revision_rank"):
        VersionCatalog([first, version("v2", 1, hour(12), hour(13))])


def test_revision_rank_cannot_reverse_source_availability_order() -> None:
    with pytest.raises(ValueError, match="contradicts rank"):
        VersionCatalog([version("v1", 1, hour(12), hour(13)), version("v2", 2, hour(10), hour(11))])


def test_equal_usable_instant_uses_explicit_revision_rank() -> None:
    catalog = VersionCatalog(
        [version("v2", 2, hour(10), hour(11)), version("v1", 1, hour(11), hour(10))]
    )
    assert catalog.latest_usable_at(KEY, hour(11)).version_id == "v2"  # type: ignore[union-attr]


def test_unsupported_retraction_is_rejected() -> None:
    ordinary = version("v1", 1, hour(10), hour(11))
    with pytest.raises(ValueError, match="retractions are not supported"):
        ObservationVersion(
            key=ordinary.key,
            version_id="v2",
            revision_rank=2,
            availability=ordinary.availability,
            source_uri=ordinary.source_uri,
            license_id=ordinary.license_id,
            content_sha256=ordinary.content_sha256,
            retracted=True,
        )


@pytest.mark.parametrize("field", ["security_id", "source_id", "observation_id"])
def test_key_identifiers_cannot_be_blank(field: str) -> None:
    fields = {"security_id": "s", "source_id": "v", "observation_id": "o"}
    fields[field] = "  "
    with pytest.raises(ValueError, match=field):
        ObservationKey(**fields)


def test_invalid_checksum_and_naive_cutoff_fail() -> None:
    ordinary = version("v1", 1, hour(10), hour(11))
    with pytest.raises(ValueError, match="content_sha256"):
        ObservationVersion(
            key=ordinary.key,
            version_id="v1",
            revision_rank=1,
            availability=ordinary.availability,
            source_uri=ordinary.source_uri,
            license_id=ordinary.license_id,
            content_sha256="not-a-digest",
            retracted=False,
        )
    with pytest.raises(ValueError, match="decision_at must be timezone-aware"):
        VersionCatalog([]).latest_usable_at(KEY, datetime(2025, 1, 3, 11))


@pytest.mark.parametrize("invalid_rank", [True, -1, 1.5])
def test_unordered_revision_ranks_fail_closed(invalid_rank: Any) -> None:
    with pytest.raises(ValueError, match="revision_rank must be a nonnegative integer"):
        replace(version("v1", 1, hour(10), hour(11)), revision_rank=invalid_rank)


@pytest.mark.parametrize(
    ("field", "invalid", "error"),
    [
        ("key", "ticker-only", "key must be an ObservationKey"),
        ("availability", None, "availability must be validated"),
        ("source_uri", " ", "source_uri must be nonblank"),
        ("license_id", " ", "license_id must be nonblank"),
        ("retracted", "false", "retracted must be a bool"),
    ],
)
def test_invalid_version_metadata_is_rejected(field: str, invalid: Any, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        replace(version("v1", 1, hour(10), hour(11)), **{field: invalid})


def test_catalog_rejects_unvalidated_members() -> None:
    with pytest.raises(ValueError, match="versions must contain ObservationVersion"):
        VersionCatalog(["raw, unvalidated record"])  # type: ignore[list-item]


def test_offsets_and_repeated_dst_hour_compare_by_instant() -> None:
    eastern = ZoneInfo("America/New_York")
    first = datetime(2025, 11, 2, 1, 30, tzinfo=eastern, fold=0)  # 05:30 UTC
    second = datetime(2025, 11, 2, 1, 15, tzinfo=eastern, fold=1)  # 06:15 UTC
    catalog = VersionCatalog([version("v1", 1, first, first), version("v2", 2, second, second)])
    assert catalog.latest_usable_at(KEY, datetime(2025, 11, 2, 6, tzinfo=UTC)).version_id == "v1"  # type: ignore[union-attr]
    assert catalog.latest_usable_at(KEY, second).version_id == "v2"  # type: ignore[union-attr]
    assert (
        catalog.latest_usable_at(
            KEY, datetime(2025, 11, 2, 1, 15, tzinfo=timezone(timedelta(hours=-5)))
        ).version_id
        == "v2"
    )  # type: ignore[union-attr]
