"""Independent receipt/provenance/time references and deterministic fault injection."""

import errno
import hashlib
import json
import os
import struct
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from quant_test.data import raw_archive
from quant_test.data.admission import (
    AcceptedAvailability,
    AvailabilityIssue,
    QuarantinedAvailability,
    RawAvailability,
    RawTimestampClaim,
    TimestampStatus,
)
from quant_test.data.raw_archive import (
    ArchiveIOError,
    LocalRawArchive,
    PayloadCorruptError,
    PayloadDigestMismatchError,
    PayloadMissingError,
    ReceiptCorruptError,
    ReceiptMissingError,
)
from quant_test.data.receipts import (
    ADMISSION_POLICY_ID,
    AdmissionReceipt,
    ReceiptFormatError,
    decode_receipt,
    encode_receipt,
)
from quant_test.data.versions import ObservationKey, ObservationVersion, VersionCatalog

ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
KEY = ObservationKey("security-1", "vendor-a", "release-2025-01-03")


def claim(value: datetime | date | None) -> RawTimestampClaim:
    return RawTimestampClaim(value, "  raw\nµ text  ", TimestampStatus.EXACT, " v1-log ", None)


def raw() -> RawAvailability:
    return RawAvailability(
        KEY,
        "v1",
        None,
        claim(datetime(2025, 1, 3, 10, tzinfo=UTC)),
        claim(datetime(2025, 1, 3, 11, tzinfo=UTC)),
        datetime(2026, 1, 1, tzinfo=UTC),
    )


def receipt(envelope: RawAvailability | None = None) -> AdmissionReceipt:
    return AdmissionReceipt(
        raw() if envelope is None else envelope,
        " https://vendor.example/v1?raw=1 ",
        " reference-license ",
        ABC,
    )


def canonical(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def test_independent_canonical_reference_and_payload_reopen(tmp_path: Path) -> None:
    # Hand-specified schema fixture, not produced by the receipt encoder.
    expected = (Path(__file__).parents[1] / "fixtures/admission-receipt-v1.json").read_bytes()
    reference_digest = "7e8aff016576493bff7d2a97733c8fb75cef76c68fafd4f9736dd7e6bda5fb1c"
    record = receipt()
    assert encode_receipt(record) == expected
    assert record.receipt_sha256 == reference_digest
    assert hashlib.sha256(expected).hexdigest() == reference_digest
    assert decode_receipt(expected) == record
    archive = LocalRawArchive(tmp_path)
    assert archive.put_receipt(record, b"abc") == reference_digest
    assert archive.put_receipt(record, b"abc") == reference_digest
    reopened = LocalRawArchive(tmp_path).get_receipt(reference_digest)
    assert reopened == record
    assert reopened.raw.event_at is None
    assert reopened.source_uri == " https://vendor.example/v1?raw=1 "
    assert reopened.license_id == " reference-license "
    assert reopened.policy_id == ADMISSION_POLICY_ID
    assert isinstance(reopened.result, AcceptedAvailability)
    assert reopened.result.availability.first_usable_at == datetime(2025, 1, 3, 11, tzinfo=UTC)
    assert reopened.result.raw is reopened.raw
    assert set(path.name for path in tmp_path.iterdir()) == {ABC, reference_digest}
    assert archive.get(ABC) == b"abc"
    # Persisted acceptance does not grant operational processing or catalog entry.
    with pytest.raises(ValueError, match="processed_at must be timezone-aware"):
        reopened.result.availability.is_available_to_platform_at(
            datetime(2026, 1, 1, tzinfo=UTC),
            processed_at=None,  # type: ignore[arg-type]
        )
    for invalid in (reopened, reopened.raw, reopened.result):
        with pytest.raises(ValueError, match="ObservationVersion"):
            VersionCatalog([invalid])  # type: ignore[list-item]
    with pytest.raises(FrozenInstanceError):
        reopened.source_uri = "changed"  # type: ignore[misc]


@pytest.mark.parametrize("value", [date(2025, 1, 3), None, datetime(2025, 1, 3, fold=1)])
def test_date_unknown_naive_and_exact_claim_text_survive_quarantine(
    tmp_path: Path, value: datetime | date | None
) -> None:
    missing = RawTimestampClaim(
        value, " unparsed original\nµ ", TimestampStatus.UNKNOWN, None, " unknown release "
    )
    record = receipt(replace(raw(), published_at=missing))
    archive = LocalRawArchive(tmp_path)
    digest = archive.put_receipt(record, b"abc")
    reopened = LocalRawArchive(tmp_path).get_receipt(digest)
    actual = reopened.raw.published_at
    assert type(actual.parsed_value) is type(value)
    assert actual == missing
    if isinstance(value, datetime):
        assert isinstance(actual.parsed_value, datetime)
        assert actual.parsed_value.fold == 1
        assert actual.parsed_value.tzinfo is None
    assert isinstance(reopened.result, QuarantinedAvailability)
    type_reason = (
        "date-only value has no exact release instant"
        if type(value) is date
        else "missing or unparsed timestamp"
        if value is None
        else "timestamp must be timezone-aware"
    )
    assert reopened.result.reasons == (
        AvailabilityIssue("published_at", "status is unknown, not exact"),
        AvailabilityIssue("published_at", type_reason),
        AvailabilityIssue("published_at", "missing nonblank evidence reference"),
        AvailabilityIssue("published_at", "timestamp uncertainty is declared"),
    )
    assert not hasattr(reopened.result, "availability")


@pytest.mark.parametrize(
    "field", ["published_at", "source_available_at", "event_at", "ingested_at"]
)
@pytest.mark.parametrize("fold", [0, 1])
@pytest.mark.parametrize("gap", [False, True])
def test_zoneinfo_folds_and_nonexistent_gaps_preserve_original_civil_rules(
    tmp_path: Path, field: str, fold: int, gap: bool
) -> None:
    civil = datetime(2025, 3, 9, 2, 30) if gap else datetime(2025, 11, 2, 1, 30)
    original = civil.replace(tzinfo=ZoneInfo("America/New_York"), fold=fold)
    value = claim(original) if field in ("published_at", "source_available_at") else original
    record = receipt(replace(raw(), **{field: value}))
    digest = LocalRawArchive(tmp_path).put_receipt(record, b"abc")
    reopened = LocalRawArchive(tmp_path).get_receipt(digest)
    actual = getattr(reopened.raw, field)
    if isinstance(actual, RawTimestampClaim):
        actual = actual.parsed_value
    assert actual.replace(tzinfo=None) == civil
    assert actual.fold == fold
    assert type(actual.tzinfo) is ZoneInfo
    assert actual.tzinfo.key == "America/New_York"
    assert actual.utcoffset() == timedelta(
        hours=(-4 if fold else -5) if gap else (-5 if fold else -4)
    )
    assert encode_receipt(reopened) == encode_receipt(record)
    if gap:
        assert isinstance(reopened.result, QuarantinedAvailability)
        assert reopened.result.reasons == (
            AvailabilityIssue(field, "timestamp is a nonexistent local time"),
        )
    else:
        assert isinstance(reopened.result, AcceptedAvailability)
        expected = datetime(2025, 11, 2, 6 if fold else 5, 30, tzinfo=UTC)
        assert actual.astimezone(UTC) == expected
        assert getattr(reopened.result.availability, field) == expected


@pytest.mark.parametrize(
    "zone",
    [
        UTC,
        timezone(timedelta(hours=5, minutes=30)),
        timezone(timedelta(seconds=-23, microseconds=-7), " exact offset name "),
        ZoneInfo("UTC"),
    ],
)
def test_utc_named_fixed_and_keyed_zones_keep_their_representation(zone: tzinfo) -> None:
    original = datetime(2025, 1, 3, 10, 2, 3, 456789, tzinfo=zone, fold=1)
    reopened = decode_receipt(encode_receipt(receipt(replace(raw(), published_at=claim(original)))))
    actual = reopened.raw.published_at.parsed_value
    assert isinstance(actual, datetime)
    assert type(actual.tzinfo) is type(zone)
    assert actual.fold == 1
    assert actual.tzname() == original.tzname()
    assert actual.utcoffset() == original.utcoffset()
    assert actual.astimezone(UTC) == original.astimezone(UTC)
    if zone is UTC:
        assert actual.tzinfo is UTC
    if isinstance(zone, ZoneInfo):
        assert isinstance(actual.tzinfo, ZoneInfo)
        assert actual.tzinfo.key == "UTC"


class CustomZone(tzinfo):
    def utcoffset(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(0)


def test_unsupported_zone_rejects_before_writes_without_narrowing_admission(tmp_path: Path) -> None:
    record = receipt(replace(raw(), event_at=datetime(2025, 1, 3, tzinfo=CustomZone())))
    assert isinstance(record.result, AcceptedAvailability)
    with pytest.raises(ValueError, match="unsupported receipt tzinfo"):
        LocalRawArchive(tmp_path).put_receipt(record, b"abc")
    assert list(tmp_path.iterdir()) == []


def test_identical_payload_different_provenance_and_amendment_quarantine(tmp_path: Path) -> None:
    archive = LocalRawArchive(tmp_path)
    first = receipt()
    amendment = receipt(
        replace(raw(), version_id="v2", published_at=replace(claim(None), evidence_reference=None))
    )
    records = [
        first,
        replace(first, source_uri="https://other.example"),
        replace(first, license_id="other-license"),
        replace(first, raw=replace(raw(), key=replace(KEY, source_id="other-source"))),
        replace(
            first,
            raw=replace(
                raw(),
                published_at=replace(
                    claim(datetime(2025, 1, 3, 10, tzinfo=UTC)),
                    evidence_reference="different-evidence",
                ),
            ),
        ),
        amendment,
    ]
    digests = [archive.put_receipt(record, b"abc") for record in records]
    assert len(set(digests)) == len(records)
    assert len(list(tmp_path.iterdir())) == len(records) + 1
    reopened = [LocalRawArchive(tmp_path).get_receipt(digest) for digest in digests]
    assert all(record.content_sha256 == ABC for record in reopened)
    assert isinstance(reopened[0].result, AcceptedAvailability)
    assert reopened[-1].raw.version_id == "v2"
    assert reopened[-1].raw.published_at.evidence_reference is None
    assert isinstance(reopened[-1].result, QuarantinedAvailability)
    admitted = reopened[0].result
    assert isinstance(admitted, AcceptedAvailability)
    validated = ObservationVersion(
        admitted.raw.key,
        admitted.raw.version_id,
        1,
        admitted.availability,
        reopened[0].source_uri,
        reopened[0].license_id,
        ABC,
        False,
    )
    catalog = VersionCatalog([validated])
    selected = catalog.latest_usable_at(KEY, datetime(2025, 1, 3, 14, tzinfo=UTC))
    assert selected is validated
    assert selected.version_id == "v1"
    assert archive.get_version(selected) == b"abc"
    with pytest.raises(ValueError, match="ObservationVersion"):
        VersionCatalog([validated, reopened[-1]])  # type: ignore[list-item]
    assert (
        AvailabilityIssue("published_at", "missing nonblank evidence reference")
        in reopened[-1].result.reasons
    )


@pytest.mark.parametrize(
    "failure", ["receipt_missing", "receipt_corrupt", "payload_missing", "payload_corrupt"]
)
def test_requested_receipt_or_payload_failure_never_falls_back(
    tmp_path: Path, failure: str
) -> None:
    archive = LocalRawArchive(tmp_path)
    older = archive.put_receipt(receipt(), b"abc")
    selected = replace(
        receipt(),
        raw=replace(raw(), version_id="v2"),
        content_sha256=hashlib.sha256(b"").hexdigest(),
    )
    digest = archive.put_receipt(selected, b"")
    target = tmp_path / (digest if failure.startswith("receipt") else selected.content_sha256)
    if failure.endswith("missing"):
        target.unlink()
    else:
        target.chmod(0o600)
        target.write_bytes(b"corrupt")
    expected = {
        "receipt_missing": ReceiptMissingError,
        "receipt_corrupt": ReceiptCorruptError,
        "payload_missing": PayloadMissingError,
        "payload_corrupt": PayloadCorruptError,
    }[failure]
    with pytest.raises(expected):
        LocalRawArchive(tmp_path).get_receipt(digest)
    assert archive.get_receipt(older).raw.version_id == "v1"


@pytest.mark.parametrize(
    "path,value",
    [
        (("schema_version",), 2),
        (("schema_version",), True),
        (("policy_id",), "unknown"),
        (("unknown",), None),
        (("raw", "extra"), 0),
        (("raw", "published_at", "status"), "maybe"),
        (("raw", "published_at", "source_text"), False),
        (("raw", "published_at", "parsed_value", "fold"), True),
        (("raw", "published_at", "parsed_value", "fold"), 2),
        (("raw", "published_at", "parsed_value", "civil"), "2025-01-03T10:00:00.000000+00:00"),
        (("raw", "published_at", "parsed_value", "timezone", "kind"), "custom"),
        (("result", "kind"), "quarantined"),
        (("result", "availability", "published_at", "civil"), "2025-01-03T09:00:00.000000"),
        (("result", "availability", "extra"), 0),
        (("content_sha256",), "A" * 64),
        (("license_id",), " "),
    ],
)
def test_rehashed_malformed_or_inconsistent_receipts_reject(
    tmp_path: Path, path: tuple[str, ...], value: Any
) -> None:
    document = json.loads(encode_receipt(receipt()))
    target = document
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    encoded = canonical(document)
    with pytest.raises(ReceiptFormatError):
        decode_receipt(encoded)
    digest = hashlib.sha256(encoded).hexdigest()
    archive = LocalRawArchive(tmp_path)
    archive.put(ABC, b"abc")
    archive.put(digest, encoded)
    with pytest.raises(ReceiptCorruptError):
        archive.get_receipt(digest)


def test_quarantine_reasons_recomputed_and_zone_rule_drift_fails() -> None:
    record = receipt(replace(raw(), published_at=claim(None)))
    document = json.loads(encode_receipt(record))
    document["result"]["reasons"][0]["reason"] = "invented reason"
    with pytest.raises(ReceiptFormatError, match="recomputed"):
        decode_receipt(canonical(document))
    record = receipt(
        replace(
            raw(),
            published_at=claim(datetime(2025, 3, 9, 2, 30, tzinfo=ZoneInfo("America/New_York"))),
        )
    )
    document = json.loads(encode_receipt(record))
    zone = document["raw"]["published_at"]["parsed_value"]["timezone"]
    zone["offset_microseconds"] = -4 * 3600 * 1_000_000  # gap fold=0 actually carries -05
    with pytest.raises(ReceiptFormatError, match="ZoneInfo rules"):
        decode_receipt(canonical(document))
    zone["key"] = "No/Such_Zone"
    with pytest.raises(ReceiptFormatError):
        decode_receipt(canonical(document))


@pytest.mark.parametrize(
    "encoded",
    [
        b"{}",
        b"null",
        b"[]",
        b"{",
        b"\xff",
        b'{"schema_version":1,"schema_version":1}',
        b'{"x":NaN}',
        b'{"x":1.0}',
    ],
)
def test_invalid_json_duplicate_fields_nonfinite_and_float_reject(encoded: bytes) -> None:
    with pytest.raises(ReceiptFormatError):
        decode_receipt(encoded)


def test_noncanonical_but_semantically_equal_json_rejects() -> None:
    with pytest.raises(ReceiptFormatError, match="canonical"):
        decode_receipt(encode_receipt(receipt()) + b"\n")


@pytest.mark.parametrize(
    "failure",
    [
        "payload_mismatch",
        "payload_cleanup",
        "receipt_create",
        "receipt_write",
        "receipt_verify",
        "receipt_link",
    ],
)
def test_prepublication_failure_has_no_receipt(
    tmp_path: Path, monkeypatch: Any, failure: str
) -> None:
    archive = LocalRawArchive(tmp_path)
    record = receipt()
    digest = record.receipt_sha256
    real_open, real_write, real_unlink = os.open, os.write, os.unlink
    real_read = LocalRawArchive._read

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise OSError(errno.EIO, "injected receipt publication failure")

    def receipt_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if flags & os.O_CREAT and (tmp_path / ABC).exists():
            return fail()
        return real_open(path, flags, *args, **kwargs)

    def receipt_write(descriptor: int, data: Any) -> int:
        if (tmp_path / ABC).exists():
            return fail()
        return real_write(descriptor, data)

    def receipt_read(directory: int, name: str, expected_digest: str) -> bytes:
        if name.startswith(".staging-") and expected_digest == digest:
            raise PayloadCorruptError("injected staged receipt verification failure")
        return real_read(directory, name, expected_digest)

    def receipt_link(source: str, destination: str, **kwargs: Any) -> None:
        assert destination == ABC or (tmp_path / ABC).read_bytes() == b"abc"
        if destination == digest:
            fail()
        os_link(source, destination, **kwargs)

    def payload_cleanup(path: Any, **kwargs: Any) -> None:
        if not (tmp_path / digest).exists():
            fail()
        real_unlink(path, **kwargs)

    os_link = os.link
    if failure == "payload_cleanup":
        monkeypatch.setattr(raw_archive.os, "unlink", payload_cleanup)
    elif failure == "receipt_create":
        monkeypatch.setattr(raw_archive.os, "open", receipt_open)
    elif failure == "receipt_write":
        monkeypatch.setattr(raw_archive.os, "write", receipt_write)
    elif failure == "receipt_verify":
        monkeypatch.setattr(LocalRawArchive, "_read", staticmethod(receipt_read))
    elif failure == "receipt_link":
        monkeypatch.setattr(raw_archive.os, "link", receipt_link)
    expected = (
        PayloadDigestMismatchError
        if failure == "payload_mismatch"
        else PayloadCorruptError
        if failure == "receipt_verify"
        else ArchiveIOError
    )
    with pytest.raises(expected):
        archive.put_receipt(record, b"bad" if failure == "payload_mismatch" else b"abc")
    assert not (tmp_path / digest).exists()
    if failure == "payload_mismatch":
        assert list(tmp_path.iterdir()) == []
    else:
        assert archive.get(ABC) == b"abc"


def test_receipt_cleanup_failure_after_link_preserves_complete_object_and_retry(
    tmp_path: Path, monkeypatch: Any
) -> None:
    archive = LocalRawArchive(tmp_path)
    record = receipt()
    real_unlink = os.unlink

    def cleanup(path: Any, **kwargs: Any) -> None:
        if (tmp_path / record.receipt_sha256).exists():
            raise PermissionError("injected post-publication cleanup failure")
        real_unlink(path, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(raw_archive.os, "unlink", cleanup)
        with pytest.raises(ArchiveIOError):
            archive.put_receipt(record, b"abc")
    assert archive.get_receipt(record.receipt_sha256) == record
    assert archive.put_receipt(record, b"abc") == record.receipt_sha256
    assert len(list(tmp_path.glob(".staging-*"))) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("raw", None),
        ("source_uri", " "),
        ("source_uri", 3),
        ("license_id", None),
        ("content_sha256", "A" * 64),
    ],
)
def test_invalid_receipt_api_arguments(field: str, value: Any) -> None:
    with pytest.raises(ValueError):
        replace(receipt(), **{field: value})


@pytest.mark.parametrize("status", [TimestampStatus.APPROXIMATE, TimestampStatus.UNVERIFIED])
def test_uncertainty_and_optional_source_text_survive_reopen(
    tmp_path: Path, status: TimestampStatus
) -> None:
    uncertain = replace(
        raw(),
        published_at=replace(
            raw().published_at,
            source_text=None,
            status=status,
            uncertainty_reason="  estimated from schedule  ",
        ),
    )
    record = receipt(uncertain)
    archive = LocalRawArchive(tmp_path)
    reopened = archive.get_receipt(archive.put_receipt(record, b"abc"))
    assert reopened.raw.published_at.source_text is None
    assert reopened.raw.published_at.status is status
    assert reopened.raw.published_at.uncertainty_reason == "  estimated from schedule  "
    assert isinstance(reopened.result, QuarantinedAvailability)
    assert reopened.result.reasons == (
        AvailabilityIssue("published_at", f"status is {status.value}, not exact"),
        AvailabilityIssue("published_at", "timestamp uncertainty is declared"),
    )


def test_file_backed_unresolvable_zone_rejects_before_writes(tmp_path: Path) -> None:
    # Independently constructed TZif v1: zero transitions, one UTC type, "UTC\0" name.
    tzif = (
        b"TZif\0"
        + b"\0" * 15
        + struct.pack(">6l", 0, 0, 0, 0, 1, 4)
        + struct.pack(">lbb", 0, 0, 0)
        + b"UTC\0"
    )
    zone = ZoneInfo.from_file(BytesIO(tzif), key="No/Such_Receipt_Zone")
    record = receipt(replace(raw(), event_at=datetime(2025, 1, 3, tzinfo=zone)))
    assert isinstance(record.result, AcceptedAvailability)
    with pytest.raises(ValueError, match="cannot be reopened"):
        LocalRawArchive(tmp_path).put_receipt(record, b"abc")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["date", "datetime"])
def test_subclass_values_reject_at_codec_without_changing_raw_constructor(kind: str) -> None:
    class CustomDate(date):
        pass

    class CustomDatetime(datetime):
        pass

    value = CustomDate(2025, 1, 3) if kind == "date" else CustomDatetime(2025, 1, 3, tzinfo=UTC)
    record = receipt(replace(raw(), published_at=claim(value)))
    with pytest.raises(ValueError, match="standard datetime/date"):
        encode_receipt(record)


@pytest.mark.parametrize("kind", ["symlink", "directory"])
def test_nonregular_receipt_object_fails_closed(tmp_path: Path, kind: str) -> None:
    digest = receipt().receipt_sha256
    target = tmp_path / digest
    if kind == "symlink":
        other = tmp_path / "other"
        other.write_bytes(encode_receipt(receipt()))
        target.symlink_to(other)
    else:
        target.mkdir()
    with pytest.raises(ReceiptCorruptError):
        LocalRawArchive(tmp_path).get_receipt(digest)


def test_missing_required_nested_field_and_nested_duplicate_reject() -> None:
    document = json.loads(encode_receipt(receipt()))
    del document["raw"]["published_at"]["source_text"]
    with pytest.raises(ReceiptFormatError):
        decode_receipt(canonical(document))
    encoded = encode_receipt(receipt()).replace(b'"fold":0', b'"fold":0,"fold":0', 1)
    with pytest.raises(ReceiptFormatError, match="duplicate"):
        decode_receipt(encoded)


def test_receipt_api_rejects_wrong_types(tmp_path: Path) -> None:
    archive = LocalRawArchive(tmp_path)
    with pytest.raises(ValueError):
        archive.put_receipt(None, b"abc")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        archive.put_receipt(receipt(), bytearray(b"abc"))  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        archive.get_receipt("INVALID")
    with pytest.raises(ReceiptFormatError):
        decode_receipt("{}")  # type: ignore[arg-type]
    assert list(tmp_path.iterdir()) == []
