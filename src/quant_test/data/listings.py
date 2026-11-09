"""In-memory historical listing identities with separate effective and knowledge time.

Histories are complete replacements per stable security/source, not deltas.
Metadata and source claims remain adapter assertions, not authenticated evidence.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise

from quant_test.data.versions import ObservationKey, ObservationVersion, VersionCatalog

LISTING_HISTORY_OBSERVATION_ID = "listing-history"


def _require_text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _utc_instant(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    utc = value.astimezone(UTC)
    roundtrip = utc.astimezone(value.tzinfo)
    if (
        roundtrip.replace(tzinfo=None) != value.replace(tzinfo=None)
        or roundtrip.utcoffset() != value.utcoffset()
    ):
        raise ValueError(f"{name} is a nonexistent local time")
    return utc


@dataclass(frozen=True, slots=True)
class ListingInterval:
    """One exact listing on the UTC half-open interval [from, until).

    An ended interval requires a nonblank source-defined end_reason, for example
    "delisted" or "symbol_changed". An open interval has no end reason. Identifiers
    are retained exactly; no case, punctuation, exchange, or currency inference
    is performed. An open end is the source's assertion, not a coverage guarantee.
    """

    issuer_id: str
    symbol: str
    venue: str
    currency: str
    effective_from: datetime
    effective_until: datetime | None = None
    end_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("issuer_id", "symbol", "venue", "currency"):
            _require_text(getattr(self, name), name)
        start = _utc_instant(self.effective_from, "effective_from")
        end = (
            None
            if self.effective_until is None
            else _utc_instant(self.effective_until, "effective_until")
        )
        if end is None:
            if self.end_reason is not None:
                raise ValueError("an open interval cannot have an end_reason")
        else:
            if end <= start:
                raise ValueError("effective_until must follow effective_from")
            _require_text(self.end_reason, "end_reason")
        object.__setattr__(self, "effective_from", start)
        object.__setattr__(self, "effective_until", end)


@dataclass(frozen=True, slots=True)
class ListingHistory:
    """One complete replacement history for version.key.security_id/source_id.

    The fixed observation ID is 'listing-history', covering all venues for that
    security and source. Empty replacements are allowed and remove all intervals
    from that version's asserted history. Older revisions remain available for
    earlier decisions; omission never triggers fallback within a selected history.
    """

    version: ObservationVersion
    intervals: tuple[ListingInterval, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.version, ObservationVersion):
            raise ValueError("version must be an ObservationVersion")
        if self.version.key.observation_id != LISTING_HISTORY_OBSERVATION_ID:
            raise ValueError("observation_id must be listing-history")
        # Existing metadata requires awareness; this boundary also rejects civil
        # times invented in a DST gap, including metadata constructed directly.
        for name in ("event_at", "published_at", "source_available_at", "ingested_at"):
            value = getattr(self.version.availability, name)
            if value is not None:
                _utc_instant(value, name)
        # An empty replacement is meaningful. Never interpret an empty string,
        # mapping, byte sequence, or unordered collection as a deletion assertion.
        if not isinstance(self.intervals, (tuple, list)):
            raise ValueError("intervals must be a tuple or list of ListingInterval records")
        intervals = tuple(self.intervals)
        by_venue: dict[str, list[ListingInterval]] = {}
        for interval in intervals:
            if not isinstance(interval, ListingInterval):
                raise ValueError("intervals must contain ListingInterval records")
            by_venue.setdefault(interval.venue, []).append(interval)
        for venue, group in by_venue.items():
            ordered = sorted(group, key=lambda item: item.effective_from)
            for previous, current in pairwise(ordered):
                if (
                    previous.effective_until is None
                    or current.effective_from < previous.effective_until
                ):
                    raise ValueError(f"overlapping listing intervals for venue {venue}")
        object.__setattr__(self, "intervals", intervals)


@dataclass(frozen=True, slots=True)
class ListingMatch:
    """A matched interval and the exact selected historical provenance."""

    interval: ListingInterval
    version: ObservationVersion


@dataclass(frozen=True, slots=True)
class ListingQueryResult:
    """A historical query, including selected metadata even when no match exists.

    selected_versions contains each eligible security/source history inspected,
    including histories without the requested venue or effective interval. An
    empty tuple means no eligible history in this catalog. Neither kind of
    absence establishes source completeness or the absence of a real listing.
    Exactly one of security_id and symbol identifies the requested lookup.
    """

    security_id: str | None
    symbol: str | None
    source_id: str
    venue: str
    effective_at: datetime
    decision_at: datetime
    selected_versions: tuple[ObservationVersion, ...]
    match: ListingMatch | None


class ListingCatalog:
    """Immutable histories selected by knowledge time before effective filtering.

    This implements historical source replay only. It does not establish local
    operational processing, source coverage, identity authenticity, or membership.
    """

    def __init__(self, histories: Iterable[ListingHistory]) -> None:
        if isinstance(histories, (str, bytes, bytearray, memoryview, Mapping)):
            raise ValueError("histories must be an iterable of ListingHistory records")
        try:
            records = tuple(histories)
        except TypeError as error:
            raise ValueError("histories must be an iterable of ListingHistory records") from error
        for record in records:
            if not isinstance(record, ListingHistory):
                raise ValueError("histories must contain ListingHistory records")
        self._versions = VersionCatalog(record.version for record in records)
        self._histories = {
            (record.version.key, record.version.version_id): record for record in records
        }
        self._keys = tuple(
            sorted(
                {record.version.key for record in records},
                key=lambda k: (k.source_id, k.security_id),
            )
        )

    def _selected(self, key: ObservationKey, decision_at: datetime) -> ListingHistory | None:
        version = self._versions.latest_usable_at(key, decision_at)
        return None if version is None else self._histories[(key, version.version_id)]

    @staticmethod
    def _query_times(effective_at: datetime, decision_at: datetime) -> tuple[datetime, datetime]:
        effective = _utc_instant(effective_at, "effective_at")
        decision = _utc_instant(decision_at, "decision_at")
        if effective > decision:
            raise ValueError("effective_at must not follow decision_at")
        return effective, decision

    @staticmethod
    def _matches(history: ListingHistory, venue: str, effective_at: datetime) -> list[ListingMatch]:
        return [
            ListingMatch(interval, history.version)
            for interval in history.intervals
            if interval.venue == venue
            and interval.effective_from <= effective_at
            and (interval.effective_until is None or effective_at < interval.effective_until)
        ]

    def listing_at(
        self,
        security_id: str,
        source_id: str,
        venue: str,
        effective_at: datetime,
        decision_at: datetime,
    ) -> ListingQueryResult:
        """Inspect one latest eligible complete history at a past/present instant."""
        for name, value in (
            ("security_id", security_id),
            ("source_id", source_id),
            ("venue", venue),
        ):
            _require_text(value, name)
        effective, decision = self._query_times(effective_at, decision_at)
        history = self._selected(
            ObservationKey(security_id, source_id, LISTING_HISTORY_OBSERVATION_ID), decision
        )
        matches = [] if history is None else self._matches(history, venue, effective)
        return ListingQueryResult(
            security_id,
            None,
            source_id,
            venue,
            effective,
            decision,
            () if history is None else (history.version,),
            matches[0] if matches else None,
        )

    def resolve_symbol_at(
        self,
        symbol: str,
        source_id: str,
        venue: str,
        effective_at: datetime,
        decision_at: datetime,
    ) -> ListingQueryResult:
        """Resolve exact symbol/source/venue; fail on multiple matching securities."""
        for name, value in (("symbol", symbol), ("source_id", source_id), ("venue", venue)):
            _require_text(value, name)
        effective, decision = self._query_times(effective_at, decision_at)
        selected: list[ObservationVersion] = []
        matches: list[ListingMatch] = []
        for key in self._keys:
            if key.source_id != source_id:
                continue
            history = self._selected(key, decision)
            if history is not None:
                selected.append(history.version)
                matches.extend(
                    match
                    for match in self._matches(history, venue, effective)
                    if match.interval.symbol == symbol
                )
        if len(matches) > 1:
            raise ValueError("ambiguous symbol resolution across securities")
        return ListingQueryResult(
            None,
            symbol,
            source_id,
            venue,
            effective,
            decision,
            tuple(selected),
            matches[0] if matches else None,
        )
