"""Validated observation versions and historical as-of selection.

Adapters must establish timestamp evidence and a source-specific revision order
before constructing these records. This module does not authenticate either.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from re import fullmatch

from quant_test.core.time import InformationAvailability


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _require_aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ObservationKey:
    """A stable security/source/observation identity, never a display ticker."""

    security_id: str
    source_id: str
    observation_id: str

    def __post_init__(self) -> None:
        for name in ("security_id", "source_id", "observation_id"):
            _require_text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class ObservationVersion:
    """One immutable source revision with validated historical availability.

    revision_rank is assigned by the source adapter from documented provider
    revision semantics. It must increase with source revision order within a key.
    The SHA-256 identifies content stored elsewhere; no mutable payload is held.
    """

    key: ObservationKey
    version_id: str
    revision_rank: int
    availability: InformationAvailability
    source_uri: str
    license_id: str
    content_sha256: str
    retracted: bool

    def __post_init__(self) -> None:
        if not isinstance(self.key, ObservationKey):
            raise ValueError("key must be an ObservationKey")
        _require_text(self.version_id, "version_id")
        if isinstance(self.revision_rank, bool) or not isinstance(self.revision_rank, int):
            raise ValueError("revision_rank must be a nonnegative integer")
        if self.revision_rank < 0:
            raise ValueError("revision_rank must be a nonnegative integer")
        if not isinstance(self.availability, InformationAvailability):
            raise ValueError("availability must be validated InformationAvailability")
        _require_text(self.source_uri, "source_uri")
        _require_text(self.license_id, "license_id")
        if (
            not isinstance(self.content_sha256, str)
            or fullmatch(r"[0-9a-f]{64}", self.content_sha256) is None
        ):
            raise ValueError("content_sha256 must be a lowercase SHA-256 hex digest")
        if not isinstance(self.retracted, bool):
            raise ValueError("retracted must be a bool")
        if self.retracted:
            raise ValueError("retractions are not supported")


class VersionCatalog:
    """A catalog of immutable versions that fails closed on ambiguous ordering."""

    def __init__(self, versions: Iterable[ObservationVersion]) -> None:
        records = tuple(versions)
        by_key: dict[ObservationKey, list[ObservationVersion]] = {}
        for record in records:
            if not isinstance(record, ObservationVersion):
                raise ValueError("versions must contain ObservationVersion records")
            by_key.setdefault(record.key, []).append(record)

        for key, group in by_key.items():
            version_ids: set[str] = set()
            ranks: set[int] = set()
            previous_usable_at: datetime | None = None
            for record in sorted(group, key=lambda item: item.revision_rank):
                if record.version_id in version_ids:
                    raise ValueError(f"duplicate version_id for {key}")
                if record.revision_rank in ranks:
                    raise ValueError(f"duplicate revision_rank for {key}")
                version_ids.add(record.version_id)
                ranks.add(record.revision_rank)
                usable_at = record.availability.first_usable_at
                if previous_usable_at is not None and usable_at < previous_usable_at:
                    raise ValueError(f"revision availability contradicts rank for {key}")
                previous_usable_at = usable_at

        self._by_key = {key: tuple(group) for key, group in by_key.items()}

    def latest_usable_at(
        self, key: ObservationKey, decision_at: datetime
    ) -> ObservationVersion | None:
        """Return the highest source revision usable at the decision instant.

        Equality at first usability is eligible. Historical backfill ingestion
        does not shift availability. No record means no eligible observation.
        """
        if not isinstance(key, ObservationKey):
            raise ValueError("key must be an ObservationKey")
        _require_aware(decision_at, "decision_at")
        eligible = (
            record
            for record in self._by_key.get(key, ())
            if record.availability.is_usable_at(decision_at)
        )
        return max(eligible, key=lambda record: record.revision_rank, default=None)
