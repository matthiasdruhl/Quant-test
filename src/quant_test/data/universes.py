"""Source-specific membership assertions and historical stable-ID listing joins.

Histories are complete replacements per security/source/universe. Neither query
results nor empty histories establish provider coverage or universe completeness.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise

from quant_test.data.listings import ListingCatalog, ListingMatch, ListingQueryResult
from quant_test.data.versions import ObservationVersion, VersionCatalog

MEMBERSHIP_HISTORY_OBSERVATION_PREFIX = "universe-membership-history:"


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


def membership_observation_id(universe_id: str) -> str:
    """Encode an exact universe ID after a fixed prefix without normalization."""
    _require_text(universe_id, "universe_id")
    return MEMBERSHIP_HISTORY_OBSERVATION_PREFIX + universe_id


@dataclass(frozen=True, slots=True)
class MembershipInterval:
    """Assert membership on the real UTC half-open interval [from, until)."""

    effective_from: datetime
    effective_until: datetime | None = None

    def __post_init__(self) -> None:
        start = _utc_instant(self.effective_from, "effective_from")
        end = (
            None
            if self.effective_until is None
            else _utc_instant(self.effective_until, "effective_until")
        )
        if end is not None and end <= start:
            raise ValueError("effective_until must follow effective_from")
        object.__setattr__(self, "effective_from", start)
        object.__setattr__(self, "effective_until", end)


@dataclass(frozen=True, slots=True)
class MembershipHistory:
    """One complete replacement membership history for a stable security.

    version.key identifies security/source and must use the observation ID from
    membership_observation_id(universe_id). An explicit empty tuple/list removes
    every interval from this revision's assertion, without older-version fallback.
    """

    universe_id: str
    version: ObservationVersion
    intervals: tuple[MembershipInterval, ...]

    def __post_init__(self) -> None:
        expected = membership_observation_id(self.universe_id)
        if not isinstance(self.version, ObservationVersion):
            raise ValueError("version must be an ObservationVersion")
        if self.version.key.observation_id != expected:
            raise ValueError("observation_id must encode the exact universe_id")
        for name in ("event_at", "published_at", "source_available_at", "ingested_at"):
            value = getattr(self.version.availability, name)
            if value is not None:
                _utc_instant(value, name)
        if not isinstance(self.intervals, (tuple, list)):
            raise ValueError("intervals must be a tuple or list of MembershipInterval records")
        intervals = tuple(self.intervals)
        for interval in intervals:
            if not isinstance(interval, MembershipInterval):
                raise ValueError("intervals must contain MembershipInterval records")
        for previous, current in pairwise(sorted(intervals, key=lambda item: item.effective_from)):
            if (
                previous.effective_until is None
                or current.effective_from < previous.effective_until
            ):
                raise ValueError("overlapping membership intervals")
        object.__setattr__(self, "intervals", intervals)


@dataclass(frozen=True, slots=True)
class MembershipMatch:
    """An asserted member interval and its selected source revision."""

    interval: MembershipInterval
    version: ObservationVersion


@dataclass(frozen=True, slots=True)
class MembershipQueryResult:
    """Asserted members and all selected revisions, including negative context.

    selected_versions retains histories without an effective membership interval.
    An empty selection means no eligible histories in this catalog, not proof of
    an empty real-world universe. Members and versions sort by stable security ID.
    These result containers do not validate a dataset when constructed directly.
    """

    universe_id: str
    source_id: str
    effective_at: datetime
    decision_at: datetime
    selected_versions: tuple[ObservationVersion, ...]
    members: tuple[MembershipMatch, ...]

    @property
    def member_ids(self) -> tuple[str, ...]:
        return tuple(member.version.key.security_id for member in self.members)


@dataclass(frozen=True, slots=True)
class UniverseListingResult:
    """Membership and one listing lookup per asserted member at the same E/D.

    listing_results preserves mapping provenance for matched and unresolved IDs.
    Membership negatives remain in membership.selected_versions. No member is
    removed because its listing ended, was corrected away, or is unavailable.
    """

    membership: MembershipQueryResult
    listing_source_id: str
    venue: str
    listing_results: tuple[ListingQueryResult, ...]

    @property
    def matches(self) -> tuple[ListingMatch, ...]:
        return tuple(result.match for result in self.listing_results if result.match is not None)

    @property
    def unresolved_member_ids(self) -> tuple[str, ...]:
        return tuple(
            member_id
            for member_id, result in zip(
                self.membership.member_ids, self.listing_results, strict=True
            )
            if result.match is None
        )


class UniverseCatalog:
    """Select historically usable complete histories before membership filtering.

    Only validated ObservationVersion metadata enters this historical replay
    boundary. Raw unknown availability belongs in data.admission quarantine.
    """

    def __init__(self, histories: Iterable[MembershipHistory]) -> None:
        if isinstance(histories, (str, bytes, bytearray, memoryview, Mapping)):
            raise ValueError("histories must be an iterable of MembershipHistory records")
        try:
            records = tuple(histories)
        except TypeError as error:
            raise ValueError(
                "histories must be an iterable of MembershipHistory records"
            ) from error
        for record in records:
            if not isinstance(record, MembershipHistory):
                raise ValueError("histories must contain MembershipHistory records")
        self._versions = VersionCatalog(record.version for record in records)
        self._histories = {
            (record.version.key, record.version.version_id): record for record in records
        }
        self._keys = tuple(
            sorted(
                {record.version.key for record in records},
                key=lambda key: (key.source_id, key.observation_id, key.security_id),
            )
        )

    def members_at(
        self,
        universe_id: str,
        source_id: str,
        effective_at: datetime,
        decision_at: datetime,
    ) -> MembershipQueryResult:
        """Return asserted IDs and positive/negative selected revision provenance."""
        observation_id = membership_observation_id(universe_id)
        _require_text(source_id, "source_id")
        effective = _utc_instant(effective_at, "effective_at")
        decision = _utc_instant(decision_at, "decision_at")
        if effective > decision:
            raise ValueError("effective_at must not follow decision_at")
        selected: list[ObservationVersion] = []
        members: list[MembershipMatch] = []
        for key in self._keys:
            if key.source_id != source_id or key.observation_id != observation_id:
                continue
            version = self._versions.latest_usable_at(key, decision)
            if version is None:
                continue
            selected.append(version)
            history = self._histories[(key, version.version_id)]
            members.extend(
                MembershipMatch(interval, version)
                for interval in history.intervals
                if interval.effective_from <= effective
                and (interval.effective_until is None or effective < interval.effective_until)
            )
        return MembershipQueryResult(
            universe_id, source_id, effective, decision, tuple(selected), tuple(members)
        )

    def listings_at(
        self,
        universe_id: str,
        source_id: str,
        listing_catalog: ListingCatalog,
        listing_source_id: str,
        venue: str,
        effective_at: datetime,
        decision_at: datetime,
    ) -> UniverseListingResult:
        """Join asserted stable IDs to an explicitly selected listing source/venue.

        Each source independently selects revisions with its own publication and
        provider timestamps against the same decision cutoff. Ingestion backfill
        does not shift historical usability. This does not authorize operational use.
        """
        if not isinstance(listing_catalog, ListingCatalog):
            raise ValueError("listing_catalog must be a ListingCatalog")
        _require_text(listing_source_id, "listing_source_id")
        _require_text(venue, "venue")
        membership = self.members_at(universe_id, source_id, effective_at, decision_at)
        results = tuple(
            listing_catalog.listing_at(
                security_id,
                listing_source_id,
                venue,
                membership.effective_at,
                membership.decision_at,
            )
            for security_id in membership.member_ids
        )
        return UniverseListingResult(membership, listing_source_id, venue, results)
