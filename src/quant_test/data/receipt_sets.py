"""Explicit raw receipt collections and reproducible assertion-quality counts.

These are inventories of raw receipts, not historically selected datasets or
coverage claims. Reports count receipt identities, never unique payloads.
"""

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from re import fullmatch
from typing import TYPE_CHECKING

from quant_test.data.admission import QuarantinedAvailability, TimestampStatus
from quant_test.data.receipts import ADMISSION_POLICY_ID, AdmissionReceipt

if TYPE_CHECKING:
    from quant_test.data.raw_archive import LocalRawArchive

RECEIPT_SET_SCHEMA_VERSION = 1
QUALITY_POLICY_ID = "raw-receipt-quality-v1"


class ReceiptSetFormatError(ValueError):
    """Malformed, unsupported, noncanonical or inconsistent receipt-set bytes."""


def _digests(values: object) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)) or type(values) not in (tuple, list):
        raise ValueError("receipt digests must be an explicit tuple or list")
    for value in values:
        if not isinstance(value, str) or fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("receipt digest must be a lowercase SHA-256 hex digest")
    if len(set(values)) != len(values):
        raise ValueError("duplicate receipt digests are not permitted")
    return tuple(sorted(values))


@dataclass(frozen=True, slots=True)
class ReceiptSetManifest:
    """Sorted, distinct receipt identities; explicit empty collections are valid."""

    receipt_sha256s: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "receipt_sha256s", _digests(self.receipt_sha256s))


def _count(value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("quality counts must be nonnegative integers")


@dataclass(frozen=True, slots=True)
class ReleaseFieldQuality:
    """Counts among all receipts for one required release field.

    Null means None, not empty/blank text. Date-only excludes datetime. Status
    counts partition all receipts independently of null/precision counts.
    """

    field: str
    parsed_value_null_count: int
    source_text_null_count: int
    evidence_reference_null_count: int
    uncertainty_reason_null_count: int
    date_only_count: int
    exact_status_count: int
    unknown_status_count: int
    approximate_status_count: int
    unverified_status_count: int

    def __post_init__(self) -> None:
        if self.field not in ("published_at", "source_available_at"):
            raise ValueError("unknown release field")
        for name, value in asdict(self).items():
            if name != "field":
                _count(value)


@dataclass(frozen=True, slots=True)
class QuarantineReasonCount:
    """Number of quarantined receipts with this exact field/reason pair."""

    field: str
    reason: str
    count: int

    def __post_init__(self) -> None:
        for value in (self.field, self.reason):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("quarantine field/reason must be nonblank text")
        _count(self.count)
        if self.count == 0:
            raise ValueError("a reported quarantine reason must occur")


@dataclass(frozen=True, slots=True)
class ReceiptSetQualityReport:
    """Immutable counts; multiple quarantine reasons can count the same receipt.

    Unknown event time and absent optional source_text are permitted assertions,
    not automatic defects. Counts establish no source coverage or completeness.
    """

    receipt_count: int
    accepted_count: int
    quarantined_count: int
    unknown_event_time_count: int
    release_fields: tuple[ReleaseFieldQuality, ...]
    quarantine_reasons: tuple[QuarantineReasonCount, ...]

    def __post_init__(self) -> None:
        for value in (
            self.receipt_count,
            self.accepted_count,
            self.quarantined_count,
            self.unknown_event_time_count,
        ):
            _count(value)
        if self.accepted_count + self.quarantined_count != self.receipt_count:
            raise ValueError("admission counts must partition receipt count")
        if self.unknown_event_time_count > self.receipt_count:
            raise ValueError("unknown event count exceeds receipt count")
        if type(self.release_fields) is not tuple or any(
            not isinstance(item, ReleaseFieldQuality) for item in self.release_fields
        ):
            raise ValueError("release_fields must be an immutable quality tuple")
        if tuple(item.field for item in self.release_fields) != (
            "published_at",
            "source_available_at",
        ):
            raise ValueError("report must contain both release fields in policy order")
        for item in self.release_fields:
            counts = asdict(item)
            if any(value > self.receipt_count for name, value in counts.items() if name != "field"):
                raise ValueError("release field count exceeds receipt count")
            if (
                sum(value for name, value in counts.items() if name.endswith("_status_count"))
                != self.receipt_count
            ):
                raise ValueError("status counts must partition receipt count")
            if item.parsed_value_null_count + item.date_only_count > self.receipt_count:
                raise ValueError("null and date-only counts must be disjoint")
        if type(self.quarantine_reasons) is not tuple or any(
            not isinstance(item, QuarantineReasonCount) for item in self.quarantine_reasons
        ):
            raise ValueError("quarantine_reasons must be an immutable reason tuple")
        pairs = tuple((item.field, item.reason) for item in self.quarantine_reasons)
        if pairs != tuple(sorted(set(pairs))):
            raise ValueError("quarantine reasons must be distinct and sorted")
        if any(item.count > self.quarantined_count for item in self.quarantine_reasons):
            raise ValueError("reason count exceeds quarantined receipt count")


@dataclass(frozen=True, slots=True)
class RawReceiptSet:
    """Manifest plus derived report; archive reopen verifies every dependency."""

    manifest: ReceiptSetManifest
    report: ReceiptSetQualityReport

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, ReceiptSetManifest) or not isinstance(
            self.report, ReceiptSetQualityReport
        ):
            raise ValueError("receipt set requires a manifest and quality report")
        if len(self.manifest.receipt_sha256s) != self.report.receipt_count:
            raise ValueError("manifest and report receipt counts differ")

    @property
    def receipt_set_sha256(self) -> str:
        return hashlib.sha256(encode_receipt_set(self)).hexdigest()


def _report(receipts: tuple[AdmissionReceipt, ...]) -> ReceiptSetQualityReport:
    release_fields: list[ReleaseFieldQuality] = []
    for name in ("published_at", "source_available_at"):
        claims = tuple(getattr(receipt.raw, name) for receipt in receipts)
        statuses = Counter(claim.status for claim in claims)
        release_fields.append(
            ReleaseFieldQuality(
                field=name,
                parsed_value_null_count=sum(claim.parsed_value is None for claim in claims),
                source_text_null_count=sum(claim.source_text is None for claim in claims),
                evidence_reference_null_count=sum(
                    claim.evidence_reference is None for claim in claims
                ),
                uncertainty_reason_null_count=sum(
                    claim.uncertainty_reason is None for claim in claims
                ),
                date_only_count=sum(type(claim.parsed_value) is date for claim in claims),
                exact_status_count=statuses[TimestampStatus.EXACT],
                unknown_status_count=statuses[TimestampStatus.UNKNOWN],
                approximate_status_count=statuses[TimestampStatus.APPROXIMATE],
                unverified_status_count=statuses[TimestampStatus.UNVERIFIED],
            )
        )
    reasons: Counter[tuple[str, str]] = Counter()
    quarantined = 0
    for receipt in receipts:
        if isinstance(receipt.result, QuarantinedAvailability):
            quarantined += 1
            # This metric counts receipts with a reason, not repeated occurrences.
            reasons.update({(issue.field, issue.reason) for issue in receipt.result.reasons})
    return ReceiptSetQualityReport(
        receipt_count=len(receipts),
        accepted_count=len(receipts) - quarantined,
        quarantined_count=quarantined,
        unknown_event_time_count=sum(receipt.raw.event_at is None for receipt in receipts),
        release_fields=tuple(release_fields),
        quarantine_reasons=tuple(
            QuarantineReasonCount(field, reason, count)
            for (field, reason), count in sorted(reasons.items())
        ),
    )


def build_receipt_set(
    archive: "LocalRawArchive", receipt_sha256s: tuple[str, ...] | list[str]
) -> RawReceiptSet:
    """Verify each explicitly supplied receipt/payload and derive deterministic counts.

    Only tuple/list inputs assert collection membership; no directory discovery,
    revision selection, fallback, or conversion to validated observations occurs.
    """
    # Local import keeps the archive/codec dependency cycle out of module loading.
    from quant_test.data.raw_archive import LocalRawArchive

    if not isinstance(archive, LocalRawArchive):
        raise ValueError("archive must be a LocalRawArchive")
    manifest = ReceiptSetManifest(_digests(receipt_sha256s))
    receipts = tuple(archive.get_receipt(digest) for digest in manifest.receipt_sha256s)
    return RawReceiptSet(manifest, _report(receipts))


def _json_bytes(document: object) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def encode_receipt_set(receipt_set: RawReceiptSet) -> bytes:
    """Encode schema-1 manifest and report together as one canonical archive object.

    This encoder does not access an archive. Publication and reopen independently
    rebuild the report from verified receipts; an encoded assertion is no proof.
    """
    if not isinstance(receipt_set, RawReceiptSet):
        raise ValueError("receipt_set must be a RawReceiptSet")
    return _json_bytes(
        {
            "schema_version": RECEIPT_SET_SCHEMA_VERSION,
            "admission_policy_id": ADMISSION_POLICY_ID,
            "quality_policy_id": QUALITY_POLICY_ID,
            "manifest": asdict(receipt_set.manifest),
            "report": asdict(receipt_set.report),
        }
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ReceiptSetFormatError("duplicate receipt-set object field")
        document[key] = value
    return document


def _reject_number(value: str) -> object:
    raise ReceiptSetFormatError(f"unsupported receipt-set number: {value}")


def decode_receipt_set(payload: bytes, archive: "LocalRawArchive") -> RawReceiptSet:
    """Strictly reopen and recompute against every verified receipt and payload.

    Dependency errors propagate as their original archive errors. Even correctly
    rehashed summary tampering rejects; the stored report must match exact bytes.
    """
    if type(payload) is not bytes:
        raise ReceiptSetFormatError("receipt-set encoding must be immutable bytes")
    try:
        document = json.loads(
            payload.decode("ascii"),
            object_pairs_hook=_unique_object,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
        if not isinstance(document, dict) or set(document) != {
            "schema_version",
            "admission_policy_id",
            "quality_policy_id",
            "manifest",
            "report",
        }:
            raise ReceiptSetFormatError("receipt-set object fields do not match schema")
        if type(document["schema_version"]) is not int or document["schema_version"] != 1:
            raise ReceiptSetFormatError("unsupported receipt-set schema version")
        if document["admission_policy_id"] != ADMISSION_POLICY_ID:
            raise ReceiptSetFormatError("unsupported admission policy")
        if document["quality_policy_id"] != QUALITY_POLICY_ID:
            raise ReceiptSetFormatError("unsupported quality policy")
        manifest = document["manifest"]
        if not isinstance(manifest, dict) or set(manifest) != {"receipt_sha256s"}:
            raise ReceiptSetFormatError("manifest fields do not match schema")
        digests = _digests(manifest["receipt_sha256s"])
        receipt_set = build_receipt_set(archive, digests)
        # Byte equality also rejects bool counts, extra/missing nested report
        # fields, reordered arrays, alternate encodings and any false summaries.
        if encode_receipt_set(receipt_set) != payload:
            raise ReceiptSetFormatError("receipt-set report differs or encoding is not canonical")
        return receipt_set
    except ReceiptSetFormatError:
        raise
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError) as error:
        raise ReceiptSetFormatError("malformed or unsupported receipt set") from error
