"""Versioned raw admission receipts; assertion retention, not evidence authentication.

The codec is intentionally narrower than the in-memory timestamp constructors:
only standard datetime/date values and naive, UTC, fixed-offset or keyed ZoneInfo
zones can be persisted. Zone rules must reproduce the recorded civil offset on
load; an offset is never substituted for a missing or changed zone.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone
from re import fullmatch
from zoneinfo import ZoneInfo

from quant_test.data.admission import (
    AcceptedAvailability,
    QuarantinedAvailability,
    RawAvailability,
    RawTimestampClaim,
    TimestampStatus,
    admit_availability,
)
from quant_test.data.versions import ObservationKey

RECEIPT_SCHEMA_VERSION = 1
ADMISSION_POLICY_ID = "raw-availability-v1"


class ReceiptFormatError(ValueError):
    """Unsupported, malformed, noncanonical or inconsistent receipt encoding."""


@dataclass(frozen=True, slots=True)
class AdmissionReceipt:
    """Bind exact payload provenance to a recomputed syntactic admission result.

    Neither an accepted receipt nor storing it creates an ObservationVersion,
    authenticates evidence/license rights, or records completed processing.
    """

    raw: RawAvailability
    source_uri: str
    license_id: str
    content_sha256: str
    policy_id: str = field(init=False, default=ADMISSION_POLICY_ID)
    result: AcceptedAvailability | QuarantinedAvailability = field(init=False)

    def __post_init__(self) -> None:
        for name in ("source_uri", "license_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be nonblank text")
        if (
            not isinstance(self.content_sha256, str)
            or fullmatch(r"[0-9a-f]{64}", self.content_sha256) is None
        ):
            raise ValueError("content_sha256 must be a lowercase SHA-256 hex digest")
        object.__setattr__(self, "result", admit_availability(self.raw))

    @property
    def receipt_sha256(self) -> str:
        """Digest of the deterministic receipt bytes, independent of payload digest."""
        return hashlib.sha256(encode_receipt(self)).hexdigest()


def _offset_microseconds(value: timedelta) -> int:
    return (value.days * 86400 + value.seconds) * 1_000_000 + value.microseconds


def _time_document(value: datetime | date | None) -> object:
    if value is None:
        return None
    if type(value) is date:
        return {"kind": "date", "value": value.isoformat()}
    if type(value) is not datetime:
        raise ValueError("receipt timestamps require standard datetime/date values")
    zone = value.tzinfo
    zone_document: object
    if zone is None:
        zone_document = None
    elif zone is UTC:
        zone_document = {"kind": "utc"}
    elif type(zone) is timezone:
        offset = value.utcoffset()
        assert offset is not None
        zone_document = {
            "kind": "fixed",
            "offset_microseconds": _offset_microseconds(offset),
            "name": value.tzname(),
        }
    elif type(zone) is ZoneInfo and isinstance(zone.key, str):
        # Reject file-backed/unresolvable keys now, before publishing any bytes.
        try:
            replayed = value.replace(tzinfo=ZoneInfo(zone.key))
        except (KeyError, ValueError) as error:
            raise ValueError("ZoneInfo key cannot be reopened for receipt persistence") from error
        if replayed.utcoffset() != value.utcoffset() or replayed.tzname() != value.tzname():
            raise ValueError("ZoneInfo key does not reproduce timestamp zone rules")
        offset = value.utcoffset()
        assert offset is not None
        zone_document = {
            "kind": "zoneinfo",
            "key": zone.key,
            "offset_microseconds": _offset_microseconds(offset),
            "name": value.tzname(),
        }
    else:
        raise ValueError("unsupported receipt tzinfo; use UTC, timezone, or keyed ZoneInfo")
    return {
        "kind": "datetime",
        "civil": value.replace(tzinfo=None).isoformat(timespec="microseconds"),
        "fold": value.fold,
        "timezone": zone_document,
    }


def _claim_document(claim: RawTimestampClaim) -> dict[str, object]:
    return {
        "parsed_value": _time_document(claim.parsed_value),
        "source_text": claim.source_text,
        "status": claim.status.value,
        "evidence_reference": claim.evidence_reference,
        "uncertainty_reason": claim.uncertainty_reason,
    }


def _result_document(result: AcceptedAvailability | QuarantinedAvailability) -> dict[str, object]:
    if isinstance(result, QuarantinedAvailability):
        return {
            "kind": "quarantined",
            "reasons": [{"field": issue.field, "reason": issue.reason} for issue in result.reasons],
        }
    availability = result.availability
    return {
        "kind": "accepted",
        "availability": {
            name: _time_document(getattr(availability, name))
            for name in ("event_at", "published_at", "source_available_at", "ingested_at")
        },
    }


def _document(receipt: AdmissionReceipt) -> dict[str, object]:
    raw = receipt.raw
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "policy_id": receipt.policy_id,
        "source_uri": receipt.source_uri,
        "license_id": receipt.license_id,
        "content_sha256": receipt.content_sha256,
        "raw": {
            "key": {
                "security_id": raw.key.security_id,
                "source_id": raw.key.source_id,
                "observation_id": raw.key.observation_id,
            },
            "version_id": raw.version_id,
            "event_at": _time_document(raw.event_at),
            "published_at": _claim_document(raw.published_at),
            "source_available_at": _claim_document(raw.source_available_at),
            "ingested_at": _time_document(raw.ingested_at),
        },
        "result": _result_document(receipt.result),
    }


def _json_bytes(document: object) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def encode_receipt(receipt: AdmissionReceipt) -> bytes:
    """Encode deterministic ASCII JSON, preserving raw precision and zone semantics."""
    if not isinstance(receipt, AdmissionReceipt):
        raise ValueError("receipt must be an AdmissionReceipt")
    return _json_bytes(_document(receipt))


def _mapping(value: object, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ReceiptFormatError("receipt object fields do not match schema")
    # JSON object keys are strings; validating here also protects internal callers.
    if any(not isinstance(key, str) for key in value):
        raise ReceiptFormatError("receipt object keys must be text")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise ReceiptFormatError("receipt field must be text")
    return value


def _optional_text(value: object) -> str | None:
    return None if value is None else _text(value)


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ReceiptFormatError("receipt field must be an integer")
    return value


def _decode_time(value: object) -> datetime | date | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ReceiptFormatError("receipt timestamp must be an object or null")
    if value.get("kind") == "date":
        document = _mapping(value, {"kind", "value"})
        text = _text(document["value"])
        parsed_date = date.fromisoformat(text)
        if parsed_date.isoformat() != text:
            raise ReceiptFormatError("noncanonical receipt date")
        return parsed_date
    document = _mapping(value, {"kind", "civil", "fold", "timezone"})
    if document["kind"] != "datetime":
        raise ReceiptFormatError("unknown receipt timestamp kind")
    civil = _text(document["civil"])
    parsed = datetime.fromisoformat(civil)
    if parsed.tzinfo is not None or parsed.isoformat(timespec="microseconds") != civil:
        raise ReceiptFormatError("civil timestamp must be canonical and contain no offset")
    fold = _integer(document["fold"])
    if fold not in (0, 1):
        raise ReceiptFormatError("fold must be 0 or 1")
    parsed = parsed.replace(fold=fold)
    zone_value = document["timezone"]
    if zone_value is None:
        return parsed
    if not isinstance(zone_value, dict):
        raise ReceiptFormatError("timezone must be an object or null")
    if zone_value.get("kind") == "utc":
        _mapping(zone_value, {"kind"})
        return parsed.replace(tzinfo=UTC)
    kind = zone_value.get("kind")
    if kind == "fixed":
        zone_document = _mapping(zone_value, {"kind", "offset_microseconds", "name"})
        zone = timezone(
            timedelta(microseconds=_integer(zone_document["offset_microseconds"])),
            _text(zone_document["name"]),
        )
        return parsed.replace(tzinfo=zone)
    if kind == "zoneinfo":
        zone_document = _mapping(zone_value, {"kind", "key", "offset_microseconds", "name"})
        zoned = parsed.replace(tzinfo=ZoneInfo(_text(zone_document["key"])))
        offset = zoned.utcoffset()
        if (
            offset is None
            or _offset_microseconds(offset) != _integer(zone_document["offset_microseconds"])
            or zoned.tzname() != _text(zone_document["name"])
        ):
            raise ReceiptFormatError("ZoneInfo rules do not match recorded civil offset/name")
        return zoned
    raise ReceiptFormatError("unknown receipt timezone kind")


def _decode_datetime(value: object, *, optional: bool = False) -> datetime | None:
    parsed = _decode_time(value)
    if parsed is None and optional:
        return None
    if not isinstance(parsed, datetime):
        raise ReceiptFormatError("envelope time must be a datetime")
    return parsed


def _decode_claim(value: object) -> RawTimestampClaim:
    document = _mapping(
        value, {"parsed_value", "source_text", "status", "evidence_reference", "uncertainty_reason"}
    )
    return RawTimestampClaim(
        parsed_value=_decode_time(document["parsed_value"]),
        source_text=_optional_text(document["source_text"]),
        status=TimestampStatus(_text(document["status"])),
        evidence_reference=_optional_text(document["evidence_reference"]),
        uncertainty_reason=_optional_text(document["uncertainty_reason"]),
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ReceiptFormatError("duplicate receipt object field")
        document[key] = value
    return document


def _reject_number(value: str) -> object:
    raise ReceiptFormatError(f"unsupported receipt number: {value}")


def decode_receipt(payload: bytes) -> AdmissionReceipt:
    """Strictly decode and recompute admission; reject unsupported policy/rule drift.

    The stored outcome, UTC fields or quarantine reasons must exactly match the
    current named policy. Canonical bytes are required, including nested fields.
    """
    if type(payload) is not bytes:
        raise ReceiptFormatError("receipt encoding must be immutable bytes")
    try:
        value: object = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
        document = _mapping(
            value,
            {
                "schema_version",
                "policy_id",
                "source_uri",
                "license_id",
                "content_sha256",
                "raw",
                "result",
            },
        )
        if _integer(document["schema_version"]) != RECEIPT_SCHEMA_VERSION:
            raise ReceiptFormatError("unsupported receipt schema version")
        if document["policy_id"] != ADMISSION_POLICY_ID:
            raise ReceiptFormatError("unsupported admission policy")
        raw_document = _mapping(
            document["raw"],
            {"key", "version_id", "event_at", "published_at", "source_available_at", "ingested_at"},
        )
        key = _mapping(raw_document["key"], {"security_id", "source_id", "observation_id"})
        ingested_at = _decode_datetime(raw_document["ingested_at"])
        assert ingested_at is not None
        raw = RawAvailability(
            key=ObservationKey(
                _text(key["security_id"]), _text(key["source_id"]), _text(key["observation_id"])
            ),
            version_id=_text(raw_document["version_id"]),
            event_at=_decode_datetime(raw_document["event_at"], optional=True),
            published_at=_decode_claim(raw_document["published_at"]),
            source_available_at=_decode_claim(raw_document["source_available_at"]),
            ingested_at=ingested_at,
        )
        receipt = AdmissionReceipt(
            raw=raw,
            source_uri=_text(document["source_uri"]),
            license_id=_text(document["license_id"]),
            content_sha256=_text(document["content_sha256"]),
        )
        # Byte comparison avoids Python's bool/int and same-zone fold equality.
        if _json_bytes(document["result"]) != _json_bytes(_result_document(receipt.result)):
            raise ReceiptFormatError("stored admission result differs from recomputed policy")
        if encode_receipt(receipt) != payload:
            raise ReceiptFormatError("receipt encoding is not canonical")
        return receipt
    except ReceiptFormatError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise ReceiptFormatError("malformed or unsupported receipt") from error
