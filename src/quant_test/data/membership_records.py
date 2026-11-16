"""Persist exact universe membership assertions against pinned observation metadata.

The link checks explicit version correspondence, not source parsing, rights or
universe completeness. Interval order and the full universe suffix are preserved.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from re import fullmatch
from typing import TYPE_CHECKING

from quant_test.data.observation_records import ReceiptLinkedVersion, encode_observation_record
from quant_test.data.universes import (
    MembershipHistory,
    MembershipInterval,
    membership_observation_id,
)

if TYPE_CHECKING:
    from quant_test.data.raw_archive import LocalRawArchive

MEMBERSHIP_HISTORY_RECORD_SCHEMA_VERSION = 1
MEMBERSHIP_POLICY_ID = "receipt-linked-membership-history-v1"


class MembershipHistoryRecordFormatError(ValueError):
    """Malformed, unsupported, noncanonical or inconsistent membership assertions."""


def _require_digest(value: str) -> None:
    if not isinstance(value, str) or fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("observation_record_sha256 must be a lowercase SHA-256 hex digest")


def _endpoint(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is not UTC:
        raise ValueError("persisted membership endpoints must be standard UTC datetimes")
    return value.replace(fold=0)


def _copy_interval(interval: MembershipInterval) -> MembershipInterval:
    if not isinstance(interval, MembershipInterval):
        raise ValueError("intervals must contain MembershipInterval records")
    return MembershipInterval(
        _endpoint(interval.effective_from),
        None if interval.effective_until is None else _endpoint(interval.effective_until),
    )


@dataclass(frozen=True, slots=True)
class MembershipHistoryRecord:
    """One exact complete replacement assertion and its normalized metadata record.

    Direct construction checks correspondence, not archive existence or source
    truth. Original interval zones were already normalized by MembershipInterval.
    """

    history: MembershipHistory
    observation_record: ReceiptLinkedVersion

    def __post_init__(self) -> None:
        if not isinstance(self.history, MembershipHistory):
            raise ValueError("history must be a MembershipHistory")
        if not isinstance(self.observation_record, ReceiptLinkedVersion):
            raise ValueError("observation_record must be a ReceiptLinkedVersion")
        supplied = ReceiptLinkedVersion(
            self.history.version, self.observation_record.receipt_sha256
        )
        if encode_observation_record(supplied) != encode_observation_record(
            self.observation_record
        ):
            raise ValueError("membership history version differs from observation record")
        normalized = MembershipHistory(
            self.history.universe_id,
            supplied.version,
            tuple(_copy_interval(interval) for interval in self.history.intervals),
        )
        object.__setattr__(self, "history", normalized)

    @property
    def observation_record_sha256(self) -> str:
        return self.observation_record.observation_record_sha256

    @property
    def membership_history_record_sha256(self) -> str:
        return hashlib.sha256(encode_membership_history_record(self)).hexdigest()


def build_membership_history_record(
    archive: "LocalRawArchive", history: MembershipHistory, observation_record_sha256: str
) -> MembershipHistoryRecord:
    """Verify existing metadata/receipt/payload and the full supplied history version."""
    from quant_test.data.raw_archive import LocalRawArchive

    if not isinstance(archive, LocalRawArchive):
        raise ValueError("archive must be a LocalRawArchive")
    if not isinstance(history, MembershipHistory):
        raise ValueError("history must be a MembershipHistory")
    _require_digest(observation_record_sha256)
    observation = archive.get_observation_record(observation_record_sha256)
    return MembershipHistoryRecord(history, observation)


def _time_text(value: datetime | None) -> str | None:
    return (
        None if value is None else value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _record_bytes(
    universe_id: str, observation_record_sha256: str, intervals: tuple[MembershipInterval, ...]
) -> bytes:
    return json.dumps(
        {
            "schema_version": MEMBERSHIP_HISTORY_RECORD_SCHEMA_VERSION,
            "membership_policy_id": MEMBERSHIP_POLICY_ID,
            "universe_id": universe_id,
            "observation_record_sha256": observation_record_sha256,
            "intervals": [
                {
                    "effective_from": _time_text(interval.effective_from),
                    "effective_until": _time_text(interval.effective_until),
                }
                for interval in intervals
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def encode_membership_history_record(record: MembershipHistoryRecord) -> bytes:
    """Encode a checked assertion, without authenticating source parsing or scope."""
    if not isinstance(record, MembershipHistoryRecord):
        raise ValueError("record must be a MembershipHistoryRecord")
    return _record_bytes(
        record.history.universe_id, record.observation_record_sha256, record.history.intervals
    )


def _mapping(value: object, fields: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise MembershipHistoryRecordFormatError("membership record fields do not match schema")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise MembershipHistoryRecordFormatError("membership field must be text")
    return value


def _decode_endpoint(value: object) -> datetime:
    parsed = datetime.fromisoformat(_text(value))
    if parsed.tzinfo is not UTC or _time_text(parsed) != value:
        raise MembershipHistoryRecordFormatError("membership timestamp must be canonical UTC")
    return parsed


def _decode_interval(value: object) -> MembershipInterval:
    fields = _mapping(value, {"effective_from", "effective_until"})
    return MembershipInterval(
        _decode_endpoint(fields["effective_from"]),
        None if fields["effective_until"] is None else _decode_endpoint(fields["effective_until"]),
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise MembershipHistoryRecordFormatError("duplicate membership record object field")
        document[key] = value
    return document


def _reject_number(value: str) -> object:
    raise MembershipHistoryRecordFormatError(f"unsupported membership record number: {value}")


def decode_membership_history_record(
    payload: bytes, archive: "LocalRawArchive"
) -> MembershipHistoryRecord:
    """Strictly reopen exact universe/interval assertions and the full dependency graph.

    Valid changed assertions are distinct, not proven provider facts. Metadata,
    receipt, payload and filesystem failures keep their existing error types.
    """
    if type(payload) is not bytes:
        raise MembershipHistoryRecordFormatError("membership encoding must be immutable bytes")
    try:
        document = _mapping(
            json.loads(
                payload.decode("ascii"),
                object_pairs_hook=_unique_object,
                parse_float=_reject_number,
                parse_constant=_reject_number,
            ),
            {
                "schema_version",
                "membership_policy_id",
                "universe_id",
                "observation_record_sha256",
                "intervals",
            },
        )
        if (
            type(document["schema_version"]) is not int
            or document["schema_version"] != MEMBERSHIP_HISTORY_RECORD_SCHEMA_VERSION
        ):
            raise MembershipHistoryRecordFormatError("unsupported membership record schema")
        if document["membership_policy_id"] != MEMBERSHIP_POLICY_ID:
            raise MembershipHistoryRecordFormatError("unsupported membership record policy")
        universe_id = _text(document["universe_id"])
        membership_observation_id(universe_id)
        digest = _text(document["observation_record_sha256"])
        _require_digest(digest)
        if type(document["intervals"]) is not list:
            raise MembershipHistoryRecordFormatError(
                "membership intervals must be an explicit array"
            )
        intervals = tuple(_decode_interval(value) for value in document["intervals"])
        if _record_bytes(universe_id, digest, intervals) != payload:
            raise MembershipHistoryRecordFormatError("membership record encoding is not canonical")
        from quant_test.data.raw_archive import LocalRawArchive

        if not isinstance(archive, LocalRawArchive):
            raise ValueError("archive must be a LocalRawArchive")
        observation = archive.get_observation_record(digest)
        record = MembershipHistoryRecord(
            MembershipHistory(universe_id, observation.version, intervals), observation
        )
        if encode_membership_history_record(record) != payload:
            raise MembershipHistoryRecordFormatError("reopened membership assertion differs")
        return record
    except MembershipHistoryRecordFormatError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise MembershipHistoryRecordFormatError(
            "malformed or inconsistent membership record"
        ) from error
