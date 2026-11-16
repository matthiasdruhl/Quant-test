"""Pin and recompute an explicit historical stable-ID universe/listing join.

The retained graph and report describe assertions, not authenticated source facts,
coverage, executable provenance or an evaluable research dataset.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from re import fullmatch
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from quant_test.data.listing_records import ListingHistoryRecord
from quant_test.data.listings import ListingCatalog
from quant_test.data.membership_records import MembershipHistoryRecord
from quant_test.data.universes import (
    UniverseCatalog,
    UniverseListingResult,
    membership_observation_id,
)

if TYPE_CHECKING:
    from quant_test.data.raw_archive import LocalRawArchive

UNIVERSE_LISTING_REPLAY_SCHEMA_VERSION = 1
REPLAY_POLICY_ID = "historical-universe-listing-replay-v1"


class UniverseListingReplayFormatError(ValueError):
    """Malformed, unsupported, noncanonical or inconsistent replay assertions."""


def _digest(value: object) -> str:
    if not isinstance(value, str) or fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("history-record digest must be lowercase SHA-256 hex")
    return value


def _digests(values: object) -> tuple[str, ...]:
    if type(values) not in (tuple, list):
        raise ValueError("history-record digests must be an explicit built-in tuple or list")
    assert isinstance(values, (tuple, list))
    checked = tuple(_digest(value) for value in values)
    if len(set(checked)) != len(checked):
        raise ValueError("duplicate history-record digests are not permitted")
    return tuple(sorted(checked))


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("replay identifiers must be nonblank text")
    return value


def _utc_instant(value: datetime, name: str) -> datetime:
    if type(value) is not datetime:
        raise ValueError(f"{name} must be a standard datetime")
    zone = value.tzinfo
    if zone is UTC or type(zone) is timezone:
        pass
    elif type(zone) is ZoneInfo and isinstance(zone.key, str):
        try:
            replayed = value.replace(tzinfo=ZoneInfo(zone.key))
        except (KeyError, ValueError) as error:
            raise ValueError(f"{name} requires a reopenable ZoneInfo key") from error
        if replayed.utcoffset() != value.utcoffset() or replayed.tzname() != value.tzname():
            raise ValueError(f"{name} ZoneInfo key does not reproduce zone rules")
    else:
        raise ValueError(f"{name} requires UTC, timezone or keyed ZoneInfo")
    if value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    try:
        utc = value.astimezone(UTC)
        roundtrip = utc.astimezone(zone)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{name} cannot be represented as a UTC instant") from error
    if (
        roundtrip.replace(tzinfo=None) != value.replace(tzinfo=None)
        or roundtrip.utcoffset() != value.utcoffset()
    ):
        raise ValueError(f"{name} is a nonexistent local time")
    return utc.replace(fold=0)


@dataclass(frozen=True, slots=True, init=False)
class UniverseListingReplayManifest:
    """Exact query filters and snapshotted sorted distinct record membership."""

    listing_history_record_sha256s: tuple[str, ...]
    membership_history_record_sha256s: tuple[str, ...]
    universe_id: str
    membership_source_id: str
    listing_source_id: str
    venue: str
    effective_at: datetime
    decision_at: datetime

    def __init__(
        self,
        listing_history_record_sha256s: tuple[str, ...] | list[str],
        membership_history_record_sha256s: tuple[str, ...] | list[str],
        universe_id: str,
        membership_source_id: str,
        listing_source_id: str,
        venue: str,
        effective_at: datetime,
        decision_at: datetime,
    ) -> None:
        listings = _digests(listing_history_record_sha256s)
        memberships = _digests(membership_history_record_sha256s)
        membership_observation_id(universe_id)
        for name, value in (
            ("universe_id", universe_id),
            ("membership_source_id", membership_source_id),
            ("listing_source_id", listing_source_id),
            ("venue", venue),
        ):
            object.__setattr__(self, name, _text(value))
        effective = _utc_instant(effective_at, "effective_at")
        decision = _utc_instant(decision_at, "decision_at")
        if effective > decision:
            raise ValueError("effective_at must not follow decision_at")
        object.__setattr__(self, "listing_history_record_sha256s", listings)
        object.__setattr__(self, "membership_history_record_sha256s", memberships)
        object.__setattr__(self, "effective_at", effective)
        object.__setattr__(self, "decision_at", decision)


@dataclass(frozen=True, slots=True)
class UniverseListingReplay:
    """All exact records plus a computed-only historical join; no archive proof."""

    manifest: UniverseListingReplayManifest
    listing_records: tuple[ListingHistoryRecord, ...]
    membership_records: tuple[MembershipHistoryRecord, ...]
    result: UniverseListingResult = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, UniverseListingReplayManifest):
            raise ValueError("manifest must be a UniverseListingReplayManifest")
        if type(self.listing_records) is not tuple or any(
            not isinstance(record, ListingHistoryRecord) for record in self.listing_records
        ):
            raise ValueError("listing_records must be an immutable tuple of listing records")
        if type(self.membership_records) is not tuple or any(
            not isinstance(record, MembershipHistoryRecord) for record in self.membership_records
        ):
            raise ValueError("membership_records must be an immutable tuple of membership records")
        if tuple(record.listing_history_record_sha256 for record in self.listing_records) != (
            self.manifest.listing_history_record_sha256s
        ) or tuple(
            record.membership_history_record_sha256 for record in self.membership_records
        ) != (self.manifest.membership_history_record_sha256s):
            raise ValueError("replay records must match manifest digests in order")
        # Validate every identity/rank/availability before any query filtering.
        listings = ListingCatalog(record.history for record in self.listing_records)
        universe = UniverseCatalog(record.history for record in self.membership_records)
        query = self.manifest
        result = universe.listings_at(
            query.universe_id,
            query.membership_source_id,
            listings,
            query.listing_source_id,
            query.venue,
            query.effective_at,
            query.decision_at,
        )
        object.__setattr__(self, "result", result)

    @property
    def universe_listing_replay_sha256(self) -> str:
        return hashlib.sha256(encode_universe_listing_replay(self)).hexdigest()


def build_universe_listing_replay(
    archive: "LocalRawArchive", manifest: UniverseListingReplayManifest
) -> UniverseListingReplay:
    """Verify every explicit history/metadata/receipt/payload, then compute the join."""
    from quant_test.data.raw_archive import LocalRawArchive

    if not isinstance(archive, LocalRawArchive):
        raise ValueError("archive must be a LocalRawArchive")
    if not isinstance(manifest, UniverseListingReplayManifest):
        raise ValueError("manifest must be a UniverseListingReplayManifest")
    listings = tuple(
        archive.get_listing_history_record(digest)
        for digest in manifest.listing_history_record_sha256s
    )
    memberships = tuple(
        archive.get_membership_history_record(digest)
        for digest in manifest.membership_history_record_sha256s
    )
    return UniverseListingReplay(manifest, listings, memberships)


def _time_text(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _manifest_document(manifest: UniverseListingReplayManifest) -> dict[str, object]:
    return {
        "listing_history_record_sha256s": manifest.listing_history_record_sha256s,
        "membership_history_record_sha256s": manifest.membership_history_record_sha256s,
        "universe_id": manifest.universe_id,
        "membership_source_id": manifest.membership_source_id,
        "listing_source_id": manifest.listing_source_id,
        "venue": manifest.venue,
        "effective_at": _time_text(manifest.effective_at),
        "decision_at": _time_text(manifest.decision_at),
    }


def _report(replay: UniverseListingReplay) -> dict[str, object]:
    memberships = {
        (record.history.version.key, record.history.version.version_id): record
        for record in replay.membership_records
    }
    listings = {
        (record.history.version.key, record.history.version.version_id): record
        for record in replay.listing_records
    }
    matched_members = {
        (match.version.key, match.version.version_id): match.interval
        for match in replay.result.membership.members
    }
    selections: list[dict[str, object]] = []
    for version in replay.result.membership.selected_versions:
        identity = (version.key, version.version_id)
        record = memberships[identity]
        interval = matched_members.get(identity)
        selections.append(
            {
                "membership_history_record_sha256": record.membership_history_record_sha256,
                "matched_interval_index": (
                    None if interval is None else record.history.intervals.index(interval)
                ),
            }
        )
    lookups: list[dict[str, object]] = []
    for lookup in replay.result.listing_results:
        selected = lookup.selected_versions
        record_listing = (
            None if not selected else listings[(selected[0].key, selected[0].version_id)]
        )
        lookups.append(
            {
                "security_id": lookup.security_id,
                "listing_history_record_sha256": (
                    None if record_listing is None else record_listing.listing_history_record_sha256
                ),
                "matched_interval_index": (
                    None
                    if record_listing is None or lookup.match is None
                    else record_listing.history.intervals.index(lookup.match.interval)
                ),
            }
        )
    return {"membership_selections": selections, "listing_lookups": lookups}


def _json_bytes(document: object) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def _document(
    manifest: UniverseListingReplayManifest, report: dict[str, object]
) -> dict[str, object]:
    return {
        "schema_version": UNIVERSE_LISTING_REPLAY_SCHEMA_VERSION,
        "replay_policy_id": REPLAY_POLICY_ID,
        "manifest": _manifest_document(manifest),
        "report": report,
    }


def encode_universe_listing_replay(replay: UniverseListingReplay) -> bytes:
    """Encode a computed assertion, without archive access or source authentication."""
    if not isinstance(replay, UniverseListingReplay):
        raise ValueError("replay must be a UniverseListingReplay")
    return _json_bytes(_document(replay.manifest, _report(replay)))


def _mapping(value: object, fields: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise UniverseListingReplayFormatError("replay fields do not match schema")
    return value


def _decode_time(value: object) -> datetime:
    parsed = datetime.fromisoformat(_text(value))
    if parsed.tzinfo is not UTC or _time_text(parsed) != value:
        raise UniverseListingReplayFormatError("replay timestamp must be canonical UTC")
    return parsed


def _array(value: object) -> list[object]:
    if type(value) is not list:
        raise UniverseListingReplayFormatError("replay field must be an explicit array")
    return value


def _index(value: object) -> None:
    if value is not None and (type(value) is not int or value < 0):
        raise UniverseListingReplayFormatError(
            "matched index must be null or a nonnegative integer"
        )


def _check_report(value: object, manifest: UniverseListingReplayManifest) -> dict[str, object]:
    report = _mapping(value, {"membership_selections", "listing_lookups"})
    selected_members: set[str] = set()
    matched_member_count = 0
    for row in _array(report["membership_selections"]):
        fields = _mapping(row, {"membership_history_record_sha256", "matched_interval_index"})
        digest = _digest(fields["membership_history_record_sha256"])
        if digest not in manifest.membership_history_record_sha256s or digest in selected_members:
            raise UniverseListingReplayFormatError("invalid or repeated selected membership digest")
        selected_members.add(digest)
        _index(fields["matched_interval_index"])
        matched_member_count += fields["matched_interval_index"] is not None
    selected_listings: set[str] = set()
    security_ids: list[str] = []
    for row in _array(report["listing_lookups"]):
        fields = _mapping(
            row, {"security_id", "listing_history_record_sha256", "matched_interval_index"}
        )
        security_ids.append(_text(fields["security_id"]))
        listing_digest = fields["listing_history_record_sha256"]
        if listing_digest is not None:
            checked = _digest(listing_digest)
            if (
                checked not in manifest.listing_history_record_sha256s
                or checked in selected_listings
            ):
                raise UniverseListingReplayFormatError(
                    "invalid or repeated selected listing digest"
                )
            selected_listings.add(checked)
        elif fields["matched_interval_index"] is not None:
            raise UniverseListingReplayFormatError("absent listing history cannot have an index")
        _index(fields["matched_interval_index"])
    if security_ids != sorted(set(security_ids)) or len(security_ids) != matched_member_count:
        raise UniverseListingReplayFormatError(
            "listing rows must be unique, sorted and match member count"
        )
    return report


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise UniverseListingReplayFormatError("duplicate replay object field")
        document[key] = value
    return document


def _reject_number(value: str) -> object:
    raise UniverseListingReplayFormatError(f"unsupported replay number: {value}")


def decode_universe_listing_replay(
    payload: bytes, archive: "LocalRawArchive"
) -> UniverseListingReplay:
    """Strictly reopen the entire graph and require exact recomputed report bytes.

    Dependency errors propagate unchanged. A failed dependency never yields a
    partial join or fallback to an older readable assertion.
    """
    if type(payload) is not bytes:
        raise UniverseListingReplayFormatError("replay encoding must be immutable bytes")
    try:
        document = _mapping(
            json.loads(
                payload.decode("ascii"),
                object_pairs_hook=_unique_object,
                parse_float=_reject_number,
                parse_constant=_reject_number,
            ),
            {"schema_version", "replay_policy_id", "manifest", "report"},
        )
        if type(document["schema_version"]) is not int or (
            document["schema_version"] != UNIVERSE_LISTING_REPLAY_SCHEMA_VERSION
        ):
            raise UniverseListingReplayFormatError("unsupported replay schema")
        if document["replay_policy_id"] != REPLAY_POLICY_ID:
            raise UniverseListingReplayFormatError("unsupported replay policy")
        fields = _mapping(
            document["manifest"],
            {
                "listing_history_record_sha256s",
                "membership_history_record_sha256s",
                "universe_id",
                "membership_source_id",
                "listing_source_id",
                "venue",
                "effective_at",
                "decision_at",
            },
        )
        manifest = UniverseListingReplayManifest(
            [_digest(value) for value in _array(fields["listing_history_record_sha256s"])],
            [_digest(value) for value in _array(fields["membership_history_record_sha256s"])],
            _text(fields["universe_id"]),
            _text(fields["membership_source_id"]),
            _text(fields["listing_source_id"]),
            _text(fields["venue"]),
            _decode_time(fields["effective_at"]),
            _decode_time(fields["decision_at"]),
        )
        report = _check_report(document["report"], manifest)
        if _json_bytes(_document(manifest, report)) != payload:
            raise UniverseListingReplayFormatError("replay encoding is not canonical")
        replay = build_universe_listing_replay(archive, manifest)
        if encode_universe_listing_replay(replay) != payload:
            raise UniverseListingReplayFormatError("recomputed replay report differs")
        return replay
    except UniverseListingReplayFormatError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise UniverseListingReplayFormatError("malformed or inconsistent replay") from error
