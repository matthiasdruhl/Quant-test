"""Point-in-time information eligibility.

The provider availability timestamp is the historically established time a source
made this version accessible, *not* the time a historical backfill was ingested.
This module validates timestamp awareness; it cannot verify vendor provenance.
"""

from dataclasses import dataclass
from datetime import UTC, datetime


def _require_aware(value: datetime, name: str) -> None:
    """Reject missing, non-datetime, and timezone-ambiguous inputs."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class InformationAvailability:
    """Version-level information times for a historically reproducible decision.

    event_at may be unknown or before/after publication (for example, a future
    event announced in advance). Public and provider availability must be proven
    before construction; uncertain raw records belong in ingestion quarantine.
    ingested_at does not retroactively restrict historical source availability.
    """

    event_at: datetime | None
    published_at: datetime
    source_available_at: datetime
    ingested_at: datetime

    def __post_init__(self) -> None:
        if self.event_at is not None:
            _require_aware(self.event_at, "event_at")
        _require_aware(self.published_at, "published_at")
        _require_aware(self.source_available_at, "source_available_at")
        _require_aware(self.ingested_at, "ingested_at")

    @property
    def first_usable_at(self) -> datetime:
        """The earliest public+source availability in UTC, not ingest time."""
        return max(self.published_at.astimezone(UTC), self.source_available_at.astimezone(UTC))

    def is_usable_at(self, decision_at: datetime) -> bool:
        """Check historical source eligibility, independently of local ingestion.

        Operational consumers must use is_available_to_platform_at instead.
        This check alone does not validate derived features or model artifacts.
        """
        _require_aware(decision_at, "decision_at")
        return self.first_usable_at <= decision_at.astimezone(UTC)

    def is_available_to_platform_at(self, decision_at: datetime, *, processed_at: datetime) -> bool:
        """Require public/source release and completed local ingestion/processing.

        processed_at is the proven time this version finished validation and
        became accessible to the consumer. It must never default to event time.
        This is an information gate, not authorization to submit an order.
        """
        _require_aware(decision_at, "decision_at")
        _require_aware(processed_at, "processed_at")
        ingested_utc = self.ingested_at.astimezone(UTC)
        processed_utc = processed_at.astimezone(UTC)
        if processed_utc < ingested_utc:
            raise ValueError("processed_at must not precede ingested_at")
        return max(self.first_usable_at, ingested_utc, processed_utc) <= decision_at.astimezone(UTC)
