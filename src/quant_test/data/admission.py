"""In-memory admission of raw availability claims, without authenticating evidence.

Adapters preserve source text and precision here before constructing validated
time metadata. Quarantine is a returned value, not durable storage or a queue.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import Enum

from quant_test.core.time import InformationAvailability
from quant_test.data.versions import ObservationKey


class TimestampStatus(Enum):
    """The adapter's assessment of a source timestamp claim."""

    EXACT = "exact"
    UNKNOWN = "unknown"
    APPROXIMATE = "approximate"
    UNVERIFIED = "unverified"


def _optional_text(value: str | None, name: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{name} must be text or None")


@dataclass(frozen=True, slots=True)
class RawTimestampClaim:
    """Preserve parsed precision and original text without parsing or inference.

    A date stays a date; None preserves missing/unparsed values. source_text
    retains original text when supplied and may be None even for an exact claim.
    A nonblank evidence_reference is only a reference supplied by the adapter,
    not proof that this module has authenticated any external evidence.
    """

    parsed_value: datetime | date | None
    source_text: str | None
    status: TimestampStatus
    evidence_reference: str | None
    uncertainty_reason: str | None

    def __post_init__(self) -> None:
        if self.parsed_value is not None and not isinstance(self.parsed_value, date):
            raise ValueError("parsed_value must be a datetime, date, or None")
        if not isinstance(self.status, TimestampStatus):
            raise ValueError("status must be a TimestampStatus")
        for name in ("source_text", "evidence_reference", "uncertainty_reason"):
            _optional_text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class RawAvailability:
    """Raw version identity and time claims; payload provenance remains separate.

    Source URI, license, checksum, revision rank, and retraction validation remain
    the responsibility of ObservationVersion and its source adapter.
    """

    key: ObservationKey
    version_id: str
    event_at: datetime | None
    published_at: RawTimestampClaim
    source_available_at: RawTimestampClaim
    ingested_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.key, ObservationKey):
            raise ValueError("key must be an ObservationKey")
        if not isinstance(self.version_id, str) or not self.version_id.strip():
            raise ValueError("version_id must be nonblank text")
        if self.event_at is not None and not isinstance(self.event_at, datetime):
            raise ValueError("event_at must be a datetime or None")
        if not isinstance(self.ingested_at, datetime):
            raise ValueError("ingested_at must be a datetime")
        for name in ("published_at", "source_available_at"):
            if not isinstance(getattr(self, name), RawTimestampClaim):
                raise ValueError(f"{name} must be a RawTimestampClaim")


@dataclass(frozen=True, slots=True)
class AvailabilityIssue:
    """One field-specific quarantine reason; raw details remain on the envelope."""

    field: str
    reason: str

    def __post_init__(self) -> None:
        for name in ("field", "reason"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be nonblank text")


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _exists_at_local_time(value: datetime) -> bool:
    """Require an aware civil time to survive a UTC roundtrip without invention.

    ZoneInfo permits construction inside a spring DST gap. Both fall folds are
    valid when their selected offsets roundtrip to the original local time.
    """
    roundtrip = value.astimezone(UTC).astimezone(value.tzinfo)
    return (
        roundtrip.replace(tzinfo=None) == value.replace(tzinfo=None)
        and roundtrip.utcoffset() == value.utcoffset()
    )


def _issues(raw: RawAvailability) -> tuple[AvailabilityIssue, ...]:
    if not isinstance(raw, RawAvailability):
        raise ValueError("raw must be a RawAvailability")
    issues: list[AvailabilityIssue] = []
    for name in ("published_at", "source_available_at"):
        claim: RawTimestampClaim = getattr(raw, name)
        if claim.status is not TimestampStatus.EXACT:
            issues.append(AvailabilityIssue(name, f"status is {claim.status.value}, not exact"))
        value = claim.parsed_value
        if value is None:
            issues.append(AvailabilityIssue(name, "missing or unparsed timestamp"))
        elif not isinstance(value, datetime):
            issues.append(AvailabilityIssue(name, "date-only value has no exact release instant"))
        elif not _aware(value):
            issues.append(AvailabilityIssue(name, "timestamp must be timezone-aware"))
        elif not _exists_at_local_time(value):
            issues.append(AvailabilityIssue(name, "timestamp is a nonexistent local time"))
        if not claim.evidence_reference or not claim.evidence_reference.strip():
            issues.append(AvailabilityIssue(name, "missing nonblank evidence reference"))
        if claim.uncertainty_reason and claim.uncertainty_reason.strip():
            issues.append(AvailabilityIssue(name, "timestamp uncertainty is declared"))
        elif claim.status is not TimestampStatus.EXACT:
            issues.append(AvailabilityIssue(name, "missing nonblank uncertainty reason"))
    for name in ("event_at", "ingested_at"):
        value = getattr(raw, name)
        if value is not None:
            if not _aware(value):
                issues.append(AvailabilityIssue(name, "timestamp must be timezone-aware"))
            elif not _exists_at_local_time(value):
                issues.append(AvailabilityIssue(name, "timestamp is a nonexistent local time"))
    return tuple(issues)


@dataclass(frozen=True, slots=True)
class AcceptedAvailability:
    """Syntactically admitted timestamps with their unchanged raw claims.

    Construction rechecks admission; callers cannot attach unrelated validated
    timestamps to a raw envelope. This does not authorize any operational use.
    """

    raw: RawAvailability
    availability: InformationAvailability = field(init=False)

    def __post_init__(self) -> None:
        if _issues(self.raw):
            raise ValueError("raw availability requires quarantine")
        publication = self.raw.published_at.parsed_value
        provider = self.raw.source_available_at.parsed_value
        # _issues rejects all other value types and naive timestamps.
        assert isinstance(publication, datetime)
        assert isinstance(provider, datetime)
        object.__setattr__(
            self,
            "availability",
            InformationAvailability(
                event_at=(None if self.raw.event_at is None else self.raw.event_at.astimezone(UTC)),
                published_at=publication.astimezone(UTC),
                source_available_at=provider.astimezone(UTC),
                ingested_at=self.raw.ingested_at.astimezone(UTC),
            ),
        )


@dataclass(frozen=True, slots=True)
class QuarantinedAvailability:
    """An in-memory rejection retaining every claim and all admission reasons."""

    raw: RawAvailability
    reasons: tuple[AvailabilityIssue, ...] = field(init=False)

    def __post_init__(self) -> None:
        reasons = _issues(self.raw)
        if not reasons:
            raise ValueError("raw availability satisfies admission")
        object.__setattr__(self, "reasons", reasons)


def admit_availability(raw: RawAvailability) -> AcceptedAvailability | QuarantinedAvailability:
    """Admit only exact, aware publication/provider claims with evidence references.

    Invalid API types raise ValueError. Valid raw claims with uncertain/missing
    timestamps return quarantine, preserving raw values rather than inventing an
    instant. Neither result persists records or authenticates external evidence.
    """
    if _issues(raw):
        return QuarantinedAvailability(raw)
    return AcceptedAvailability(raw)
