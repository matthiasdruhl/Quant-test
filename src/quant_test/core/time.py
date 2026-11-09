"""Point-in-time information eligibility.

The provider availability timestamp is the historically established time a source
made this version accessible, *not* the time a historical backfill was ingested.
This module validates timestamp awareness; it cannot verify vendor provenance.
"""

from dataclasses import dataclass
from datetime import datetime


def _require_aware(value: datetime, name: str) -> None:
    """Reject naive datetime inputs, whose timezone interpretation is ambiguous."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class InformationAvailability:
    """Version-level information times for a historically reproducible decision.

    event_at may be before or after publication (for example, a future event
    announced in advance). ingested_at is retained for lineage, but does not
    retroactively define when historical observers could have seen the record.
    """

    event_at: datetime
    published_at: datetime
    source_available_at: datetime
    ingested_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.event_at, "event_at")
        _require_aware(self.published_at, "published_at")
        _require_aware(self.source_available_at, "source_available_at")
        _require_aware(self.ingested_at, "ingested_at")

    @property
    def first_usable_at(self) -> datetime:
        """The earliest validated public+source availability, not ingest time."""
        return max(self.published_at, self.source_available_at)

    def is_usable_at(self, decision_at: datetime) -> bool:
        """Return whether the record could be used in a decision at this time."""
        _require_aware(decision_at, "decision_at")
        return self.first_usable_at <= decision_at
