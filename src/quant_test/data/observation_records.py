"""Persist explicit version assertions linked to raw receipts, without authentication.

Direct construction/encoding checks metadata shape only. Archive publication and
reopen verify the exact existing receipt/payload and repeat every shared-field
check. An accepted receipt alone never creates an ObservationVersion.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from re import fullmatch
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from quant_test.core.time import InformationAvailability
from quant_test.data.admission import AcceptedAvailability
from quant_test.data.versions import ObservationKey, ObservationVersion

if TYPE_CHECKING:
    from quant_test.data.raw_archive import LocalRawArchive

OBSERVATION_RECORD_SCHEMA_VERSION = 1
LINKAGE_POLICY_ID = "receipt-linked-observation-v1"
_TIME_FIELDS = ("event_at", "published_at", "source_available_at", "ingested_at")


class ObservationRecordFormatError(ValueError):
    """Malformed, unsupported, noncanonical or inconsistent metadata bytes."""


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


def _normalized_version(version: ObservationVersion) -> ObservationVersion:
    if not isinstance(version, ObservationVersion):
        raise ValueError("version must be an ObservationVersion")
    if type(version.revision_rank) is not int:
        raise ValueError("revision_rank must be a standard nonnegative integer")
    availability = version.availability
    normalized = InformationAvailability(
        event_at=(
            None
            if availability.event_at is None
            else _utc_instant(availability.event_at, "event_at")
        ),
        published_at=_utc_instant(availability.published_at, "published_at"),
        source_available_at=_utc_instant(availability.source_available_at, "source_available_at"),
        ingested_at=_utc_instant(availability.ingested_at, "ingested_at"),
    )
    return ObservationVersion(
        version.key,
        version.version_id,
        version.revision_rank,
        normalized,
        version.source_uri,
        version.license_id,
        version.content_sha256,
        version.retracted,
    )


@dataclass(frozen=True, slots=True)
class ReceiptLinkedVersion:
    """An explicit version assertion and receipt identity, not verified source truth.

    The version is copied with UTC timestamps. Direct construction cannot verify
    that a receipt exists or matches; use build_observation_record or archive APIs.
    """

    version: ObservationVersion
    receipt_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.receipt_sha256, str)
            or fullmatch(r"[0-9a-f]{64}", self.receipt_sha256) is None
        ):
            raise ValueError("receipt_sha256 must be a lowercase SHA-256 hex digest")
        object.__setattr__(self, "version", _normalized_version(self.version))

    @property
    def observation_record_sha256(self) -> str:
        return hashlib.sha256(encode_observation_record(self)).hexdigest()


def build_observation_record(
    archive: "LocalRawArchive", version: ObservationVersion, receipt_sha256: str
) -> ReceiptLinkedVersion:
    """Verify existing receipt/payload and all shared assertions before publication.

    Source rank and provenance are still caller assertions. No raw or accepted
    receipt is promoted into a version and no operational completion is inferred.
    """
    from quant_test.data.raw_archive import LocalRawArchive

    if not isinstance(archive, LocalRawArchive):
        raise ValueError("archive must be a LocalRawArchive")
    record = ReceiptLinkedVersion(version, receipt_sha256)
    receipt = archive.get_receipt(receipt_sha256)
    if not isinstance(receipt.result, AcceptedAvailability):
        raise ValueError("observation record requires an accepted receipt")
    supplied = record.version
    for name, actual, expected in (
        ("key", supplied.key, receipt.raw.key),
        ("version_id", supplied.version_id, receipt.raw.version_id),
        ("source_uri", supplied.source_uri, receipt.source_uri),
        ("license_id", supplied.license_id, receipt.license_id),
        ("content_sha256", supplied.content_sha256, receipt.content_sha256),
    ):
        if actual != expected:
            raise ValueError(f"observation {name} differs from receipt")
    for name in _TIME_FIELDS:
        # Both envelopes are UTC here: same-zone datetime equality cannot hide folds.
        if getattr(supplied.availability, name) != getattr(receipt.result.availability, name):
            raise ValueError(f"observation {name} differs from receipt")
    return record


def _time_text(value: datetime | None) -> str | None:
    return (
        None if value is None else value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _json_bytes(document: object) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def encode_observation_record(record: ReceiptLinkedVersion) -> bytes:
    """Encode schema-1 assertions without checking receipt existence or authenticity."""
    if not isinstance(record, ReceiptLinkedVersion):
        raise ValueError("record must be a ReceiptLinkedVersion")
    version = record.version
    return _json_bytes(
        {
            "schema_version": OBSERVATION_RECORD_SCHEMA_VERSION,
            "linkage_policy_id": LINKAGE_POLICY_ID,
            "receipt_sha256": record.receipt_sha256,
            "version": {
                "key": {
                    "security_id": version.key.security_id,
                    "source_id": version.key.source_id,
                    "observation_id": version.key.observation_id,
                },
                "version_id": version.version_id,
                "revision_rank": version.revision_rank,
                "availability": {
                    name: _time_text(getattr(version.availability, name)) for name in _TIME_FIELDS
                },
                "source_uri": version.source_uri,
                "license_id": version.license_id,
                "content_sha256": version.content_sha256,
                "retracted": version.retracted,
            },
        }
    )


def _mapping(value: object, fields: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ObservationRecordFormatError("observation record fields do not match schema")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ObservationRecordFormatError("observation record field must be text")
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ObservationRecordFormatError("observation record field must be an integer")
    return value


def _decode_time(value: object, *, optional: bool = False) -> datetime | None:
    if value is None and optional:
        return None
    parsed = datetime.fromisoformat(_text(value))
    if parsed.tzinfo is not UTC or _time_text(parsed) != value:
        raise ObservationRecordFormatError("observation timestamp must be canonical UTC")
    return parsed


def _required_time(value: object) -> datetime:
    parsed = _decode_time(value)
    assert parsed is not None
    return parsed


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ObservationRecordFormatError("duplicate observation record object field")
        document[key] = value
    return document


def _reject_number(value: str) -> object:
    raise ObservationRecordFormatError(f"unsupported observation record number: {value}")


def decode_observation_record(payload: bytes, archive: "LocalRawArchive") -> ReceiptLinkedVersion:
    """Strictly reopen explicit metadata and reverify exact receipt/payload linkage.

    Dependency archive failures retain their original types; malformed metadata
    and mismatched assertions become ObservationRecordFormatError.
    """
    if type(payload) is not bytes:
        raise ObservationRecordFormatError("observation record encoding must be immutable bytes")
    try:
        document = _mapping(
            json.loads(
                payload.decode("ascii"),
                object_pairs_hook=_unique_object,
                parse_float=_reject_number,
                parse_constant=_reject_number,
            ),
            {"schema_version", "linkage_policy_id", "receipt_sha256", "version"},
        )
        if _integer(document["schema_version"]) != OBSERVATION_RECORD_SCHEMA_VERSION:
            raise ObservationRecordFormatError("unsupported observation record schema version")
        if document["linkage_policy_id"] != LINKAGE_POLICY_ID:
            raise ObservationRecordFormatError("unsupported observation linkage policy")
        fields = _mapping(
            document["version"],
            {
                "key",
                "version_id",
                "revision_rank",
                "availability",
                "source_uri",
                "license_id",
                "content_sha256",
                "retracted",
            },
        )
        key = _mapping(fields["key"], {"security_id", "source_id", "observation_id"})
        times = _mapping(fields["availability"], set(_TIME_FIELDS))
        retracted = fields["retracted"]
        if type(retracted) is not bool:
            raise ObservationRecordFormatError("retracted must be a bool")
        version = ObservationVersion(
            ObservationKey(
                _text(key["security_id"]), _text(key["source_id"]), _text(key["observation_id"])
            ),
            _text(fields["version_id"]),
            _integer(fields["revision_rank"]),
            InformationAvailability(
                _decode_time(times["event_at"], optional=True),
                _required_time(times["published_at"]),
                _required_time(times["source_available_at"]),
                _required_time(times["ingested_at"]),
            ),
            _text(fields["source_uri"]),
            _text(fields["license_id"]),
            _text(fields["content_sha256"]),
            retracted,
        )
        record = ReceiptLinkedVersion(version, _text(document["receipt_sha256"]))
        if encode_observation_record(record) != payload:
            raise ObservationRecordFormatError("observation record encoding is not canonical")
        return build_observation_record(archive, record.version, record.receipt_sha256)
    except ObservationRecordFormatError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise ObservationRecordFormatError(
            "malformed or inconsistent observation record"
        ) from error
