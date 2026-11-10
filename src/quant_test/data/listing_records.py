"""Persist explicit listing intervals pinned to an existing observation record.

The link verifies version correspondence, not that an adapter parsed the source
payload correctly. Interval order and exact text remain caller assertions.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from re import fullmatch
from typing import TYPE_CHECKING

from quant_test.data.listings import ListingHistory, ListingInterval
from quant_test.data.observation_records import ReceiptLinkedVersion, encode_observation_record

if TYPE_CHECKING:
    from quant_test.data.raw_archive import LocalRawArchive

LISTING_HISTORY_RECORD_SCHEMA_VERSION = 1
LISTING_POLICY_ID = "receipt-linked-listing-history-v1"


class ListingHistoryRecordFormatError(ValueError):
    """Malformed, unsupported, noncanonical or inconsistent listing assertions."""


def _require_digest(value: str) -> None:
    if not isinstance(value, str) or fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("observation_record_sha256 must be a lowercase SHA-256 hex digest")


def _endpoint(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is not UTC:
        raise ValueError("persisted listing endpoints must be standard UTC datetimes")
    return value.replace(fold=0)


def _copy_interval(interval: ListingInterval) -> ListingInterval:
    if not isinstance(interval, ListingInterval):
        raise ValueError("intervals must contain ListingInterval records")
    return ListingInterval(
        interval.issuer_id,
        interval.symbol,
        interval.venue,
        interval.currency,
        _endpoint(interval.effective_from),
        None if interval.effective_until is None else _endpoint(interval.effective_until),
        interval.end_reason,
    )


@dataclass(frozen=True, slots=True)
class ListingHistoryRecord:
    """A complete interval assertion with its exact normalized metadata dependency.

    Direct construction checks correspondence, not archive existence or source
    truth. Existing interval UTC normalization has already lost original zones.
    """

    history: ListingHistory
    observation_record: ReceiptLinkedVersion

    def __post_init__(self) -> None:
        if not isinstance(self.history, ListingHistory):
            raise ValueError("history must be a ListingHistory")
        if not isinstance(self.observation_record, ReceiptLinkedVersion):
            raise ValueError("observation_record must be a ReceiptLinkedVersion")
        supplied = ReceiptLinkedVersion(
            self.history.version, self.observation_record.receipt_sha256
        )
        if encode_observation_record(supplied) != encode_observation_record(
            self.observation_record
        ):
            raise ValueError("listing history version differs from observation record")
        normalized = ListingHistory(
            supplied.version, tuple(_copy_interval(interval) for interval in self.history.intervals)
        )
        object.__setattr__(self, "history", normalized)

    @property
    def observation_record_sha256(self) -> str:
        return self.observation_record.observation_record_sha256

    @property
    def listing_history_record_sha256(self) -> str:
        return hashlib.sha256(encode_listing_history_record(self)).hexdigest()


def build_listing_history_record(
    archive: "LocalRawArchive", history: ListingHistory, observation_record_sha256: str
) -> ListingHistoryRecord:
    """Verify existing metadata/receipt/payload and all supplied version assertions."""
    from quant_test.data.raw_archive import LocalRawArchive

    if not isinstance(archive, LocalRawArchive):
        raise ValueError("archive must be a LocalRawArchive")
    if not isinstance(history, ListingHistory):
        raise ValueError("history must be a ListingHistory")
    _require_digest(observation_record_sha256)
    observation = archive.get_observation_record(observation_record_sha256)
    return ListingHistoryRecord(history, observation)


def _time_text(value: datetime | None) -> str | None:
    return (
        None if value is None else value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _record_bytes(observation_record_sha256: str, intervals: tuple[ListingInterval, ...]) -> bytes:
    return json.dumps(
        {
            "schema_version": LISTING_HISTORY_RECORD_SCHEMA_VERSION,
            "listing_policy_id": LISTING_POLICY_ID,
            "observation_record_sha256": observation_record_sha256,
            "intervals": [
                {
                    "issuer_id": interval.issuer_id,
                    "symbol": interval.symbol,
                    "venue": interval.venue,
                    "currency": interval.currency,
                    "effective_from": _time_text(interval.effective_from),
                    "effective_until": _time_text(interval.effective_until),
                    "end_reason": interval.end_reason,
                }
                for interval in intervals
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def encode_listing_history_record(record: ListingHistoryRecord) -> bytes:
    """Encode a checked assertion without proving archive existence or source parsing."""
    if not isinstance(record, ListingHistoryRecord):
        raise ValueError("record must be a ListingHistoryRecord")
    return _record_bytes(record.observation_record_sha256, record.history.intervals)


def _mapping(value: object, fields: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ListingHistoryRecordFormatError("listing record fields do not match schema")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ListingHistoryRecordFormatError("listing field must be text")
    return value


def _decode_endpoint(value: object) -> datetime:
    parsed = datetime.fromisoformat(_text(value))
    if parsed.tzinfo is not UTC or _time_text(parsed) != value:
        raise ListingHistoryRecordFormatError("listing timestamp must be canonical UTC")
    return parsed


def _decode_interval(value: object) -> ListingInterval:
    fields = _mapping(
        value,
        {
            "issuer_id",
            "symbol",
            "venue",
            "currency",
            "effective_from",
            "effective_until",
            "end_reason",
        },
    )
    return ListingInterval(
        _text(fields["issuer_id"]),
        _text(fields["symbol"]),
        _text(fields["venue"]),
        _text(fields["currency"]),
        _decode_endpoint(fields["effective_from"]),
        None if fields["effective_until"] is None else _decode_endpoint(fields["effective_until"]),
        None if fields["end_reason"] is None else _text(fields["end_reason"]),
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ListingHistoryRecordFormatError("duplicate listing record object field")
        document[key] = value
    return document


def _reject_number(value: str) -> object:
    raise ListingHistoryRecordFormatError(f"unsupported listing record number: {value}")


def decode_listing_history_record(
    payload: bytes, archive: "LocalRawArchive"
) -> ListingHistoryRecord:
    """Reopen explicit intervals against pinned metadata, preserving dependency errors.

    Valid changes create new assertions; this decoder cannot authenticate that
    intervals were derived correctly from the referenced source payload.
    """
    if type(payload) is not bytes:
        raise ListingHistoryRecordFormatError("listing encoding must be immutable bytes")
    try:
        document = _mapping(
            json.loads(
                payload.decode("ascii"),
                object_pairs_hook=_unique_object,
                parse_float=_reject_number,
                parse_constant=_reject_number,
            ),
            {"schema_version", "listing_policy_id", "observation_record_sha256", "intervals"},
        )
        if type(document["schema_version"]) is not int or (
            document["schema_version"] != LISTING_HISTORY_RECORD_SCHEMA_VERSION
        ):
            raise ListingHistoryRecordFormatError("unsupported listing record schema")
        if document["listing_policy_id"] != LISTING_POLICY_ID:
            raise ListingHistoryRecordFormatError("unsupported listing record policy")
        digest = _text(document["observation_record_sha256"])
        _require_digest(digest)
        if type(document["intervals"]) is not list:
            raise ListingHistoryRecordFormatError("listing intervals must be an explicit array")
        intervals = tuple(_decode_interval(value) for value in document["intervals"])
        if _record_bytes(digest, intervals) != payload:
            raise ListingHistoryRecordFormatError("listing record encoding is not canonical")
        from quant_test.data.raw_archive import LocalRawArchive

        if not isinstance(archive, LocalRawArchive):
            raise ValueError("archive must be a LocalRawArchive")
        observation = archive.get_observation_record(digest)
        record = ListingHistoryRecord(ListingHistory(observation.version, intervals), observation)
        if encode_listing_history_record(record) != payload:
            raise ListingHistoryRecordFormatError("reopened listing assertion differs")
        return record
    except ListingHistoryRecordFormatError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise ListingHistoryRecordFormatError("malformed or inconsistent listing record") from error
