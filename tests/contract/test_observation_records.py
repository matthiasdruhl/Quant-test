"""Independent receipt-linkage, canonical metadata, temporal and failure references."""

import errno
import hashlib
import json
import os
import stat
import struct
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from quant_test.core.time import InformationAvailability
from quant_test.data import raw_archive
from quant_test.data.admission import AcceptedAvailability, RawTimestampClaim, TimestampStatus
from quant_test.data.observation_records import (
    ObservationRecordFormatError,
    ReceiptLinkedVersion,
    build_observation_record,
    decode_observation_record,
    encode_observation_record,
)
from quant_test.data.raw_archive import (
    ArchiveIOError,
    LocalRawArchive,
    ObservationRecordCorruptError,
    ObservationRecordMissingError,
    PayloadCorruptError,
    PayloadMissingError,
    ReceiptCorruptError,
    ReceiptMissingError,
)
from quant_test.data.receipts import AdmissionReceipt, decode_receipt
from quant_test.data.versions import ObservationKey, ObservationVersion, VersionCatalog

ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
RECEIPT = "7e8aff016576493bff7d2a97733c8fb75cef76c68fafd4f9736dd7e6bda5fb1c"
RECORD = "0ddcac3235946f348116ab136b11b9a9548171f88249e7c299bfbb5178fdbfeb"
FIXTURES = Path(__file__).parents[1] / "fixtures"
TIME_FIELDS = ("event_at", "published_at", "source_available_at", "ingested_at")


def receipt() -> AdmissionReceipt:
    return decode_receipt((FIXTURES / "admission-receipt-v1.json").read_bytes())


def version() -> ObservationVersion:
    return ObservationVersion(
        ObservationKey("security-1", "vendor-a", "release-2025-01-03"),
        "v1",
        0,
        InformationAvailability(
            None,
            datetime(2025, 1, 3, 10, tzinfo=UTC),
            datetime(2025, 1, 3, 11, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        ),
        " https://vendor.example/v1?raw=1 ",
        " reference-license ",
        ABC,
        False,
    )


def canonical(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def publish_bytes(archive: LocalRawArchive, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    archive.put(digest, payload)
    return digest


def prepare(tmp_path: Path) -> LocalRawArchive:
    archive = LocalRawArchive(tmp_path)
    assert archive.put_receipt(receipt(), b"abc") == RECEIPT
    return archive


def test_literal_canonical_reference_and_complete_reopen(tmp_path: Path) -> None:
    expected = (FIXTURES / "observation-record-v1.json").read_bytes()
    assert hashlib.sha256(expected).hexdigest() == RECORD
    supplied = version()
    archive = prepare(tmp_path)
    record = build_observation_record(archive, supplied, RECEIPT)
    assert encode_observation_record(record) == expected
    assert record.observation_record_sha256 == RECORD
    assert record.version == supplied
    assert record.version is not supplied
    assert record.version.source_uri == " https://vendor.example/v1?raw=1 "
    assert record.version.license_id == " reference-license "
    assert record.version.availability.event_at is None
    assert archive.put_observation_record(supplied, RECEIPT) == RECORD
    assert archive.put_observation_record(supplied, RECEIPT) == RECORD
    assert LocalRawArchive(tmp_path).get_observation_record(RECORD) == record
    assert decode_observation_record(expected, archive) == record
    assert {path.name for path in tmp_path.iterdir()} == {ABC, RECEIPT, RECORD}
    # Existing version helpers still address only payload bytes.
    assert archive.put_version(supplied, b"abc") is None
    assert archive.get_version(supplied) == b"abc"
    with pytest.raises(FrozenInstanceError):
        record.receipt_sha256 = "f" * 64  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        record.version.revision_rank = 1  # type: ignore[misc]


def test_bare_construction_encoding_and_rank_do_not_authenticate_linkage(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    asserted = replace(version(), source_uri="unrelated assertion")
    record = ReceiptLinkedVersion(asserted, RECEIPT)
    encoded = encode_observation_record(record)
    with pytest.raises(ObservationRecordFormatError, match="inconsistent"):
        decode_observation_record(encoded, archive)
    with pytest.raises(ObservationRecordCorruptError):
        archive.get_observation_record(publish_bytes(archive, encoded))
    # Rank is explicitly asserted by the caller, not authenticated by receipt time.
    other = replace(version(), revision_rank=17)
    reopened = archive.get_observation_record(archive.put_observation_record(other, RECEIPT))
    assert reopened.version.revision_rank == 17
    assert reopened.version.availability.first_usable_at == datetime(2025, 1, 3, 11, tzinfo=UTC)
    with pytest.raises(ValueError, match="duplicate version_id"):
        VersionCatalog([version(), reopened.version])


@pytest.mark.parametrize("field", ["security_id", "source_id", "observation_id"])
def test_each_exact_key_component_must_match(tmp_path: Path, field: str) -> None:
    archive = prepare(tmp_path)
    changed = replace(version(), key=replace(version().key, **{field: "different"}))
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError, match="key differs"):
        archive.put_observation_record(changed, RECEIPT)
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize(
    "field,value",
    [
        ("version_id", "v2"),
        ("source_uri", "https://vendor.example/v1?raw=1"),
        ("source_uri", " https://vendor.example/v1?raw=2 "),
        ("license_id", "reference-license"),
        ("license_id", " REFERENCE-LICENSE "),
        ("content_sha256", "f" * 64),
    ],
)
def test_each_exact_provenance_assertion_must_match(tmp_path: Path, field: str, value: str) -> None:
    archive = prepare(tmp_path)
    changed = replace(version(), **{field: value})
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError, match=f"{field} differs"):
        archive.put_observation_record(changed, RECEIPT)
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize("field", TIME_FIELDS)
def test_every_timestamp_and_unknown_event_must_match(tmp_path: Path, field: str) -> None:
    archive = prepare(tmp_path)
    original = version()
    current = getattr(original.availability, field)
    changed = (
        datetime(2025, 1, 1, tzinfo=UTC) if current is None else current + timedelta(microseconds=1)
    )
    mismatched = replace(original, availability=replace(original.availability, **{field: changed}))
    with pytest.raises(ValueError, match=f"{field} differs"):
        archive.put_observation_record(mismatched, RECEIPT)
    if field == "event_at":
        with_event = replace(receipt(), raw=replace(receipt().raw, event_at=changed))
        digest = archive.put_receipt(with_event, b"abc")
        with pytest.raises(ValueError, match="event_at differs"):
            archive.put_observation_record(original, digest)


@pytest.mark.parametrize("field", TIME_FIELDS)
def test_equivalent_offsets_normalize_every_field_without_changing_receipt(
    tmp_path: Path, field: str
) -> None:
    archive = prepare(tmp_path)
    supplied = version()
    offset = timezone(timedelta(hours=5, minutes=30), "named offset")
    if field == "event_at":
        event = datetime(2025, 1, 2, 10, tzinfo=UTC)
        raw_receipt = replace(receipt(), raw=replace(receipt().raw, event_at=event))
        digest = archive.put_receipt(raw_receipt, b"abc")
        supplied = replace(supplied, availability=replace(supplied.availability, event_at=event))
    else:
        digest = RECEIPT
    instant = getattr(supplied.availability, field)
    equivalent = replace(
        supplied, availability=replace(supplied.availability, **{field: instant.astimezone(offset)})
    )
    assert archive.put_observation_record(supplied, digest) == archive.put_observation_record(
        equivalent, digest
    )
    result = archive.get_observation_record(archive.put_observation_record(equivalent, digest))
    assert getattr(result.version.availability, field).tzinfo is UTC
    assert getattr(result.version.availability, field).fold == 0
    assert archive.get_receipt(digest).receipt_sha256 == digest


@pytest.mark.parametrize("field", TIME_FIELDS)
@pytest.mark.parametrize("fold,expected_hour", [(0, 5), (1, 6)])
def test_real_dst_folds_match_only_their_independent_utc_instant(
    tmp_path: Path, field: str, fold: int, expected_hour: int
) -> None:
    archive = LocalRawArchive(tmp_path)
    local = datetime(2025, 11, 2, 1, 30, tzinfo=ZoneInfo("America/New_York"), fold=fold)
    expected = datetime(2025, 11, 2, expected_hour, 30, tzinfo=UTC)
    raw = receipt().raw
    if field in ("published_at", "source_available_at"):
        raw = replace(raw, **{field: replace(getattr(raw, field), parsed_value=local)})
    else:
        raw = replace(raw, **{field: local})
    raw_receipt = replace(receipt(), raw=raw)
    digest = archive.put_receipt(raw_receipt, b"abc")
    assert isinstance(raw_receipt.result, AcceptedAvailability)
    supplied = replace(version(), availability=raw_receipt.result.availability)
    local_version = replace(supplied, availability=replace(supplied.availability, **{field: local}))
    reopened = archive.get_observation_record(archive.put_observation_record(local_version, digest))
    assert getattr(reopened.version.availability, field) == expected
    other_fold = local.replace(fold=1 - fold)
    assert local == other_fold  # Python's wall-clock equality must not mask a mismatch.
    wrong = replace(supplied, availability=replace(supplied.availability, **{field: other_fold}))
    with pytest.raises(ValueError, match=f"{field} differs"):
        archive.put_observation_record(wrong, digest)


@pytest.mark.parametrize("field", TIME_FIELDS)
@pytest.mark.parametrize("fold", [0, 1])
def test_gap_rejects_before_normalizing_even_if_it_matches_a_real_receipt(
    tmp_path: Path, field: str, fold: int
) -> None:
    archive = LocalRawArchive(tmp_path)
    gap = datetime(2025, 3, 9, 2, 30, tzinfo=ZoneInfo("America/New_York"), fold=fold)
    real = datetime(2025, 3, 9, 7 if fold == 0 else 6, 30, tzinfo=UTC)
    assert gap.astimezone(UTC) == real
    raw = receipt().raw
    if field in ("published_at", "source_available_at"):
        raw = replace(raw, **{field: replace(getattr(raw, field), parsed_value=real)})
    else:
        raw = replace(raw, **{field: real})
    raw_receipt = replace(receipt(), raw=raw)
    digest = archive.put_receipt(raw_receipt, b"abc")
    assert isinstance(raw_receipt.result, AcceptedAvailability)
    supplied = replace(
        version(), availability=replace(raw_receipt.result.availability, **{field: gap})
    )
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError, match="nonexistent"):
        archive.put_observation_record(supplied, digest)
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize("field", ["published_at", "source_available_at"])
@pytest.mark.parametrize("parsed", [None, date(2025, 1, 3)])
def test_unknown_or_date_only_receipt_never_promotes(
    tmp_path: Path, field: str, parsed: date | None
) -> None:
    archive = LocalRawArchive(tmp_path)
    uncertain = RawTimestampClaim(parsed, "source date", TimestampStatus.UNKNOWN, None, "unproven")
    quarantined = replace(receipt(), raw=replace(receipt().raw, **{field: uncertain}))
    digest = archive.put_receipt(quarantined, b"abc")
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError, match="accepted receipt"):
        archive.put_observation_record(version(), digest)
    asserted = encode_observation_record(ReceiptLinkedVersion(version(), digest))
    with pytest.raises(ObservationRecordFormatError):
        decode_observation_record(asserted, archive)
    assert set(tmp_path.iterdir()) == before


class DatetimeSubclass(datetime):
    pass


class IntegerSubclass(int):
    pass


def test_persistence_rejects_integer_subclasses_without_changing_version_contract() -> None:
    supplied = replace(version(), revision_rank=IntegerSubclass(1))
    assert supplied.revision_rank == 1
    with pytest.raises(ValueError, match="standard nonnegative integer"):
        ReceiptLinkedVersion(supplied, RECEIPT)


class OtherTimezone(tzinfo):
    def utcoffset(self, value: datetime | None) -> timedelta:
        return timedelta(0)

    def dst(self, value: datetime | None) -> timedelta:
        return timedelta(0)


@pytest.mark.parametrize("field", TIME_FIELDS)
@pytest.mark.parametrize(
    "unsupported",
    [DatetimeSubclass(2025, 1, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=OtherTimezone())],
)
def test_unsupported_timestamp_boundary_does_not_narrow_existing_metadata(
    field: str, unsupported: datetime
) -> None:
    supplied = replace(
        version(), availability=replace(version().availability, **{field: unsupported})
    )
    assert getattr(supplied.availability, field) is unsupported
    with pytest.raises(ValueError):
        ReceiptLinkedVersion(supplied, RECEIPT)


@pytest.mark.parametrize(
    "extreme",
    [
        datetime.min.replace(tzinfo=timezone(timedelta(hours=1))),
        datetime.max.replace(tzinfo=timezone(-timedelta(hours=1))),
    ],
)
def test_offset_utc_overflow_rejects_as_value_error(extreme: datetime) -> None:
    supplied = replace(
        version(), availability=replace(version().availability, published_at=extreme)
    )
    with pytest.raises(ValueError, match="cannot be represented"):
        ReceiptLinkedVersion(supplied, RECEIPT)


@pytest.mark.parametrize(
    "key,name,error",
    [
        ("No/Such_Observation_Zone", "UTC", "reopenable"),
        ("America/New_York", "UTC", "zone rules"),
        ("UTC", "GMT", "zone rules"),
    ],
)
def test_keyed_zone_must_reopen_with_same_offset_and_name(
    tmp_path: Path, key: str, name: str, error: str
) -> None:
    # Independent TZif v1 with zero transitions and one zero-offset named type.
    # A claimed key cannot replace this original zone's actual offset or name.
    abbreviation = name.encode("ascii") + b"\0"
    tzif = (
        b"TZif\0"
        + b"\0" * 15
        + struct.pack(">6l", 0, 0, 0, 0, 1, len(abbreviation))
        + struct.pack(">lbb", 0, 0, 0)
        + abbreviation
    )
    zone = ZoneInfo.from_file(BytesIO(tzif), key=key)
    claimed = datetime(2025, 1, 3, 10, tzinfo=zone)
    assert claimed.utcoffset() == timedelta(0)
    supplied = replace(
        version(), availability=replace(version().availability, published_at=claimed)
    )
    archive = prepare(tmp_path)
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError, match=error):
        archive.put_observation_record(supplied, RECEIPT)
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize("invalid", [None, "version", (), {}, [], receipt(), receipt().result])
def test_explicit_observation_version_is_required(invalid: Any) -> None:
    with pytest.raises(ValueError, match="ObservationVersion"):
        ReceiptLinkedVersion(invalid, RECEIPT)


@pytest.mark.parametrize("invalid", [None, b"a" * 64, "A" * 64, "../object", "a" * 63, [], True])
def test_invalid_digest_arguments_reject(tmp_path: Path, invalid: Any) -> None:
    archive = LocalRawArchive(tmp_path)
    with pytest.raises(ValueError):
        ReceiptLinkedVersion(version(), invalid)
    with pytest.raises(ValueError):
        archive.get_observation_record(invalid)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("invalid", [None, "archive", {}, object()])
def test_invalid_archive_argument_rejects(invalid: Any) -> None:
    with pytest.raises(ValueError, match="LocalRawArchive"):
        build_observation_record(invalid, version(), RECEIPT)
    with pytest.raises(ObservationRecordFormatError):
        decode_observation_record((FIXTURES / "observation-record-v1.json").read_bytes(), invalid)


@pytest.mark.parametrize("invalid", [None, (), {}, [], version(), receipt()])
def test_encoder_requires_explicit_record(invalid: Any) -> None:
    with pytest.raises(ValueError, match="ReceiptLinkedVersion"):
        encode_observation_record(invalid)


@pytest.mark.parametrize("invalid", [None, "{}", bytearray(b"{}"), memoryview(b"{}")])
def test_decoder_requires_immutable_bytes(tmp_path: Path, invalid: Any) -> None:
    with pytest.raises(ObservationRecordFormatError, match="immutable bytes"):
        decode_observation_record(invalid, LocalRawArchive(tmp_path))


@pytest.mark.parametrize(
    "path,value",
    [
        (("schema_version",), 2),
        (("schema_version",), True),
        (("linkage_policy_id",), "unknown"),
        (("receipt_sha256",), "f" * 64),
        (("version", "key", "security_id"), "another"),
        (("version", "key", "source_id"), "another"),
        (("version", "key", "observation_id"), "another"),
        (("version", "version_id"), "v2"),
        (("version", "source_uri"), "another"),
        (("version", "license_id"), "another"),
        (("version", "content_sha256"), "f" * 64),
        (("version", "retracted"), True),
        (("version", "retracted"), 0),
        (("version", "revision_rank"), True),
        (("version", "revision_rank"), 1.0),
        (("version", "revision_rank"), -1),
        (("version", "revision_rank"), "1"),
        (("version", "availability", "event_at"), "2025-01-01T00:00:00.000000Z"),
        (("version", "availability", "published_at"), None),
        (("version", "availability", "published_at"), "2025-01-03T10:00:00Z"),
        (("version", "availability", "published_at"), "2025-01-03T10:00:00.000000+00:00"),
        (("version", "availability", "published_at"), "2025-01-03T11:00:00.000000+01:00"),
        (("version", "availability", "published_at"), "2025-01-03T10:00:00.000001Z"),
        (("version", "availability", "published_at"), "2025-01-03"),
        (("version", "availability", "source_available_at"), "2025-01-03T11:00:00.000001Z"),
        (("version", "availability", "ingested_at"), "2026-01-01T00:00:00.000001Z"),
    ],
)
def test_rehashed_tampering_rejects_metadata_but_dependency_errors_keep_type(
    tmp_path: Path, path: tuple[str, ...], value: Any
) -> None:
    archive = prepare(tmp_path)
    document = json.loads((FIXTURES / "observation-record-v1.json").read_bytes())
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    encoded = canonical(document)
    error = ReceiptMissingError if path == ("receipt_sha256",) else ObservationRecordFormatError
    with pytest.raises(error):
        decode_observation_record(encoded, archive)
    digest = publish_bytes(archive, encoded)
    archive_error = (
        ReceiptMissingError if path == ("receipt_sha256",) else ObservationRecordCorruptError
    )
    with pytest.raises(archive_error):
        archive.get_observation_record(digest)


@pytest.mark.parametrize(
    "location", [(), ("version",), ("version", "key"), ("version", "availability")]
)
@pytest.mark.parametrize("mutation", ["unknown", "missing"])
def test_strict_nested_field_sets_reject(
    tmp_path: Path, location: tuple[str, ...], mutation: str
) -> None:
    archive = prepare(tmp_path)
    document = json.loads((FIXTURES / "observation-record-v1.json").read_bytes())
    target = document
    for key in location:
        target = target[key]
    if mutation == "unknown":
        target["extra"] = None
    else:
        target.pop(next(iter(target)))
    with pytest.raises(ObservationRecordFormatError):
        decode_observation_record(canonical(document), archive)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value + b"\n",
        lambda value: b" " + value,
        lambda value: value.replace(
            b'"schema_version":1', b'"schema_version":1,"schema_version":1'
        ),
        lambda value: value.replace(b'"version_id":"v1"', b'"version_id":"v1","version_id":"v1"'),
        lambda value: json.dumps(json.loads(value), indent=2).encode("ascii"),
        lambda value: value.replace(b'"revision_rank":0', b'"revision_rank":NaN'),
        lambda value: value.replace(b'"revision_rank":0', b'"revision_rank":Infinity'),
        lambda value: b"\xff",
    ],
)
def test_duplicate_noncanonical_and_invalid_json_rejects(tmp_path: Path, mutate: Any) -> None:
    archive = prepare(tmp_path)
    encoded = mutate((FIXTURES / "observation-record-v1.json").read_bytes())
    with pytest.raises(ObservationRecordFormatError):
        decode_observation_record(encoded, archive)


@pytest.mark.parametrize(
    "target,error",
    [
        ("metadata", ObservationRecordMissingError),
        ("receipt", ReceiptMissingError),
        ("payload", PayloadMissingError),
    ],
)
def test_missing_selected_dependency_never_falls_back(
    tmp_path: Path, target: str, error: type[Exception]
) -> None:
    archive = prepare(tmp_path)
    assert archive.put_observation_record(version(), RECEIPT) == RECORD
    digest = {"metadata": RECORD, "receipt": RECEIPT, "payload": ABC}[target]
    (tmp_path / digest).unlink()
    with pytest.raises(error):
        archive.get_observation_record(RECORD)
    if target != "metadata":
        before = set(tmp_path.iterdir())
        with pytest.raises(error):
            archive.put_observation_record(version(), RECEIPT)
        assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize(
    "target,error",
    [
        ("metadata", ObservationRecordCorruptError),
        ("receipt", ReceiptCorruptError),
        ("payload", PayloadCorruptError),
    ],
)
def test_corrupt_objects_never_repair_or_substitute(
    tmp_path: Path, target: str, error: type[Exception]
) -> None:
    archive = prepare(tmp_path)
    assert archive.put_observation_record(version(), RECEIPT) == RECORD
    path = tmp_path / {"metadata": RECORD, "receipt": RECEIPT, "payload": ABC}[target]
    path.chmod(0o600)
    path.write_bytes(b"corrupt")
    with pytest.raises(error):
        archive.get_observation_record(RECORD)
    with pytest.raises(error if target != "metadata" else PayloadCorruptError):
        archive.put_observation_record(version(), RECEIPT)
    assert path.read_bytes() == b"corrupt"


@pytest.mark.parametrize("kind", ["directory", "symlink", "fifo"])
def test_nonregular_metadata_rejects_without_following_or_blocking(
    tmp_path: Path, kind: str
) -> None:
    archive = prepare(tmp_path)
    path = tmp_path / RECORD
    if kind == "directory":
        path.mkdir()
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.symlink_to(tmp_path / RECEIPT)
    with pytest.raises(ObservationRecordCorruptError):
        archive.get_observation_record(RECORD)
    assert archive.get_receipt(RECEIPT) == receipt()


def test_dependencies_are_verified_before_any_metadata_publication(
    tmp_path: Path, monkeypatch: Any
) -> None:
    archive = prepare(tmp_path)
    (tmp_path / ABC).unlink()

    def forbidden_put(*args: Any, **kwargs: Any) -> None:
        pytest.fail("metadata publication attempted before payload verification")

    monkeypatch.setattr(archive, "put", forbidden_put)
    with pytest.raises(PayloadMissingError):
        archive.put_observation_record(version(), RECEIPT)
    assert not (tmp_path / RECORD).exists()


@pytest.mark.parametrize("failure", ["create", "write", "file_close", "verify", "link"])
def test_prepublication_failure_exposes_no_metadata(
    tmp_path: Path, monkeypatch: Any, failure: str
) -> None:
    archive = prepare(tmp_path)
    real_open, real_close = os.open, os.close
    real_read = LocalRawArchive._read

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise OSError(errno.EIO, "injected metadata publication failure")

    def fail_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        if flags & os.O_CREAT:
            return fail()
        return real_open(path, flags, *args, **kwargs)

    def fail_verify(directory: int, name: str, digest: str) -> bytes:
        if name.startswith(".staging-") and digest == RECORD:
            raise PayloadCorruptError("injected staged metadata verification failure")
        return real_read(directory, name, digest)

    def fail_file_close(descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        is_metadata_stage = stat.S_ISREG(metadata.st_mode) and metadata.st_size == len(
            (FIXTURES / "observation-record-v1.json").read_bytes()
        )
        real_close(descriptor)
        if is_metadata_stage:
            raise OSError(errno.EIO, "injected staged metadata close failure")

    if failure == "create":
        monkeypatch.setattr(raw_archive.os, "open", fail_open)
    elif failure == "write":
        monkeypatch.setattr(raw_archive.os, "write", fail)
    elif failure == "file_close":
        monkeypatch.setattr(raw_archive.os, "close", fail_file_close)
    elif failure == "verify":
        monkeypatch.setattr(LocalRawArchive, "_read", staticmethod(fail_verify))
    else:
        monkeypatch.setattr(raw_archive.os, "link", fail)
    with pytest.raises(PayloadCorruptError if failure == "verify" else ArchiveIOError):
        archive.put_observation_record(version(), RECEIPT)
    assert not (tmp_path / RECORD).exists()
    assert archive.get_receipt(RECEIPT) == receipt()


@pytest.mark.parametrize("failure", ["cleanup", "directory_close"])
def test_postpublication_failure_leaves_complete_metadata_and_retry_verifies(
    tmp_path: Path, monkeypatch: Any, failure: str
) -> None:
    archive = prepare(tmp_path)
    real_unlink, real_close = os.unlink, os.close

    def fail_cleanup(path: Any, **kwargs: Any) -> None:
        raise OSError(errno.EIO, "injected metadata cleanup failure")

    def fail_directory_close(descriptor: int) -> None:
        # Directory close immediately after publication; close first to avoid a leak.
        is_directory = (tmp_path / RECORD).exists() and stat.S_ISDIR(os.fstat(descriptor).st_mode)
        real_close(descriptor)
        if is_directory:
            raise OSError(errno.EIO, "injected metadata directory-close failure")

    with monkeypatch.context() as patch:
        if failure == "cleanup":
            patch.setattr(raw_archive.os, "unlink", fail_cleanup)
        else:
            patch.setattr(raw_archive.os, "close", fail_directory_close)
        with pytest.raises(ArchiveIOError):
            archive.put_observation_record(version(), RECEIPT)
    assert (tmp_path / RECORD).read_bytes() == (
        FIXTURES / "observation-record-v1.json"
    ).read_bytes()
    assert archive.get_observation_record(RECORD).version == version()
    assert archive.put_observation_record(version(), RECEIPT) == RECORD
    assert len(list(tmp_path.glob(".staging-*"))) == (1 if failure == "cleanup" else 0)
    assert real_unlink is os.unlink


def test_filesystem_dependency_failure_propagates(tmp_path: Path, monkeypatch: Any) -> None:
    archive = prepare(tmp_path)
    assert archive.put_observation_record(version(), RECEIPT) == RECORD

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise ArchiveIOError("injected dependency I/O failure")

    monkeypatch.setattr(archive, "get_receipt", fail)
    with pytest.raises(ArchiveIOError, match="dependency I/O"):
        archive.get_observation_record(RECORD)
    with pytest.raises(ArchiveIOError, match="dependency I/O"):
        archive.put_observation_record(version(), RECEIPT)


def test_reopened_versions_keep_historical_cutoffs_and_explicit_processing_gate(
    tmp_path: Path,
) -> None:
    archive = prepare(tmp_path)
    first = archive.get_observation_record(
        archive.put_observation_record(version(), RECEIPT)
    ).version
    later_receipt = replace(
        receipt(),
        raw=replace(
            receipt().raw,
            version_id="v2",
            published_at=replace(
                receipt().raw.published_at, parsed_value=datetime(2025, 1, 4, 10, tzinfo=UTC)
            ),
            source_available_at=replace(
                receipt().raw.source_available_at, parsed_value=datetime(2025, 1, 4, 11, tzinfo=UTC)
            ),
        ),
    )
    later_digest = archive.put_receipt(later_receipt, b"abc")
    assert isinstance(later_receipt.result, AcceptedAvailability)
    second_supplied = replace(
        version(), version_id="v2", revision_rank=1, availability=later_receipt.result.availability
    )
    second = archive.get_observation_record(
        archive.put_observation_record(second_supplied, later_digest)
    ).version
    catalog = VersionCatalog([second, first])
    assert (
        catalog.latest_usable_at(first.key, datetime(2025, 1, 4, 10, 59, 59, tzinfo=UTC)) == first
    )
    assert catalog.latest_usable_at(first.key, datetime(2025, 1, 4, 11, tzinfo=UTC)) == second
    assert first.availability.is_usable_at(datetime(2025, 1, 3, 11, tzinfo=UTC))
    assert not first.availability.is_available_to_platform_at(
        datetime(2025, 1, 3, 11, tzinfo=UTC), processed_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    with pytest.raises(ValueError):
        first.availability.is_available_to_platform_at(
            datetime(2026, 1, 2, tzinfo=UTC), processed_at=None
        )  # type: ignore[arg-type]
