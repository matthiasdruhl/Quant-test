"""Independent explicit inventory, historical selection and failure references."""

import errno
import hashlib
import json
import os
import stat
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from quant_test.data import raw_archive
from quant_test.data.admission import AcceptedAvailability
from quant_test.data.catalog_inventories import (
    VersionCatalogInventory,
    VersionCatalogInventoryFormatError,
    VersionCatalogManifest,
    build_version_catalog_inventory,
    decode_version_catalog_inventory,
    encode_version_catalog_inventory,
)
from quant_test.data.observation_records import ReceiptLinkedVersion
from quant_test.data.raw_archive import (
    ArchiveIOError,
    LocalRawArchive,
    ObservationRecordCorruptError,
    ObservationRecordMissingError,
    PayloadCorruptError,
    PayloadMissingError,
    ReceiptCorruptError,
    ReceiptMissingError,
    VersionCatalogInventoryCorruptError,
    VersionCatalogInventoryMissingError,
)
from quant_test.data.receipts import AdmissionReceipt, decode_receipt
from quant_test.data.versions import ObservationKey, ObservationVersion

ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
RECEIPT = "7e8aff016576493bff7d2a97733c8fb75cef76c68fafd4f9736dd7e6bda5fb1c"
RECORD = "0ddcac3235946f348116ab136b11b9a9548171f88249e7c299bfbb5178fdbfeb"
INVENTORY = "662ab9c810efdbc1e6ba3877edc430dd696c33975125f4b7a9d03d7a5c147f30"
FIXTURES = Path(__file__).parents[1] / "fixtures"


def receipt() -> AdmissionReceipt:
    return decode_receipt((FIXTURES / "admission-receipt-v1.json").read_bytes())


def publish_record(
    archive: LocalRawArchive, supplied_receipt: AdmissionReceipt | None = None, rank: int = 0
) -> tuple[str, ObservationVersion]:
    selected = receipt() if supplied_receipt is None else supplied_receipt
    assert isinstance(selected.result, AcceptedAvailability)
    supplied = ObservationVersion(
        selected.raw.key,
        selected.raw.version_id,
        rank,
        selected.result.availability,
        selected.source_uri,
        selected.license_id,
        selected.content_sha256,
        False,
    )
    receipt_digest = archive.put_receipt(selected, b"abc")
    return archive.put_observation_record(supplied, receipt_digest), supplied


def prepare(tmp_path: Path) -> tuple[LocalRawArchive, ObservationVersion]:
    archive = LocalRawArchive(tmp_path)
    record_digest, supplied = publish_record(archive)
    assert record_digest == RECORD
    return archive, supplied


def canonical(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def inventory_bytes(digests: list[str]) -> bytes:
    return canonical(
        {
            "schema_version": 1,
            "catalog_policy_id": "observation-version-catalog-v1",
            "manifest": {"observation_record_sha256s": sorted(digests)},
        }
    )


def publish_bytes(archive: LocalRawArchive, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    archive.put(digest, payload)
    return digest


def changed_release(version_id: str, day: int, source_uri: str | None = None) -> AdmissionReceipt:
    original = receipt()
    return replace(
        original,
        source_uri=original.source_uri if source_uri is None else source_uri,
        raw=replace(
            original.raw,
            version_id=version_id,
            published_at=replace(
                original.raw.published_at, parsed_value=datetime(2025, 1, day, 10, tzinfo=UTC)
            ),
            source_available_at=replace(
                original.raw.source_available_at,
                parsed_value=datetime(2025, 1, day, 11, tzinfo=UTC),
            ),
        ),
    )


def test_independent_literal_manifest_and_reopen(tmp_path: Path) -> None:
    archive, supplied = prepare(tmp_path)
    expected = (FIXTURES / "version-catalog-inventory-v1.json").read_bytes()
    assert hashlib.sha256(expected).hexdigest() == INVENTORY
    inventory = build_version_catalog_inventory(archive, [RECORD])
    assert encode_version_catalog_inventory(inventory) == expected
    assert inventory.version_catalog_inventory_sha256 == INVENTORY
    assert inventory.manifest.observation_record_sha256s == (RECORD,)
    assert len(inventory.records) == 1
    assert inventory.records[0].version == supplied
    assert inventory.records[0].receipt_sha256 == RECEIPT
    assert inventory.records[0].observation_record_sha256 == RECORD
    assert archive.put_version_catalog_inventory([RECORD]) == INVENTORY
    assert archive.put_version_catalog_inventory((RECORD,)) == INVENTORY
    reopened = LocalRawArchive(tmp_path).get_version_catalog_inventory(INVENTORY)
    assert reopened == inventory
    assert decode_version_catalog_inventory(expected, archive) == inventory
    assert inventory.to_catalog() is not inventory.to_catalog()
    assert (
        inventory.to_catalog().latest_usable_at(supplied.key, datetime(2025, 1, 3, 11, tzinfo=UTC))
        == supplied
    )
    assert {path.name for path in tmp_path.iterdir()} == {ABC, RECEIPT, RECORD, INVENTORY}
    for value, field in (
        (inventory, "records"),
        (inventory.manifest, "observation_record_sha256s"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(value, field, ())


def test_explicit_empty_inventory_includes_no_unmentioned_objects(tmp_path: Path) -> None:
    archive, supplied = prepare(tmp_path)
    empty = build_version_catalog_inventory(archive, [])
    assert empty.records == ()
    assert empty.manifest.observation_record_sha256s == ()
    assert encode_version_catalog_inventory(empty) == inventory_bytes([])
    digest = archive.put_version_catalog_inventory([])
    assert archive.put_version_catalog_inventory(()) == digest
    reopened = archive.get_version_catalog_inventory(digest)
    assert reopened == empty
    assert (
        reopened.to_catalog().latest_usable_at(supplied.key, datetime(2026, 1, 1, tzinfo=UTC))
        is None
    )
    assert archive.get_observation_record(RECORD).version == supplied


def test_order_input_snapshot_sorted_provenance_and_same_payload_identity(tmp_path: Path) -> None:
    archive, first = prepare(tmp_path)
    second_digest, second = publish_record(archive, changed_release("v2", 4), 1)
    supplied = [second_digest, RECORD]
    inventory = build_version_catalog_inventory(archive, supplied)
    supplied.clear()
    expected = tuple(sorted((RECORD, second_digest)))
    assert inventory.manifest.observation_record_sha256s == expected
    assert tuple(record.observation_record_sha256 for record in inventory.records) == expected
    assert {record.version.version_id for record in inventory.records} == {"v1", "v2"}
    assert {record.version.content_sha256 for record in inventory.records} == {ABC}
    assert len({record.receipt_sha256 for record in inventory.records}) == 2
    assert archive.put_version_catalog_inventory(
        [RECORD, second_digest]
    ) == archive.put_version_catalog_inventory([second_digest, RECORD])
    assert {record.version for record in inventory.records} == {first, second}
    values = [second_digest, RECORD]
    manifest = VersionCatalogManifest(values)
    values.clear()
    assert manifest.observation_record_sha256s == expected


class ListSubclass(list[str]):
    pass


class TupleSubclass(tuple[str, ...]):
    pass


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        RECORD,
        b"",
        b"a" * 64,
        bytearray(),
        memoryview(b""),
        {},
        set(),
        frozenset(),
        iter(()),
        True,
        1,
        ListSubclass(),
        TupleSubclass(),
        [None],
        [True],
        [b"a" * 64],
        ["A" * 64],
        ["a" * 63],
        ["../object"],
        [RECORD, RECORD],
        [RECORD, "not a digest"],
    ],
)
def test_invalid_membership_rejects_before_any_dependency_access(
    tmp_path: Path, monkeypatch: Any, invalid: Any
) -> None:
    archive = LocalRawArchive(tmp_path)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("invalid membership caused archive access")

    monkeypatch.setattr(archive, "get_observation_record", forbidden)
    with pytest.raises(ValueError):
        VersionCatalogManifest(invalid)
    with pytest.raises(ValueError):
        build_version_catalog_inventory(archive, invalid)
    with pytest.raises(ValueError):
        archive.put_version_catalog_inventory(invalid)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("invalid", [None, "archive", {}, object()])
def test_empty_collection_still_requires_valid_archive(invalid: Any) -> None:
    with pytest.raises(ValueError, match="LocalRawArchive"):
        build_version_catalog_inventory(invalid, [])
    with pytest.raises(VersionCatalogInventoryFormatError):
        decode_version_catalog_inventory(inventory_bytes([]), invalid)


@pytest.mark.parametrize("conflict", ["version_id", "rank", "availability", "same_receipt_rank"])
def test_conflicting_record_assertions_fail_without_deduplication_or_publication(
    tmp_path: Path, conflict: str
) -> None:
    archive, first = prepare(tmp_path)
    if conflict == "version_id":
        # Distinct receipt identity and rank do not excuse a duplicate version ID.
        other_receipt = changed_release("v1", 4, "different source URI assertion")
        rank, expected = 1, "duplicate version_id"
    elif conflict == "rank":
        other_receipt = changed_release("v2", 4)
        rank, expected = 0, "duplicate revision_rank"
    elif conflict == "availability":
        other_receipt = changed_release("v2", 2)
        rank, expected = 1, "contradicts rank"
    else:
        other_receipt = receipt()
        rank, expected = 1, "duplicate version_id"
    second_digest, _ = publish_record(archive, other_receipt, rank)
    assert second_digest != RECORD
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError, match=expected):
        archive.put_version_catalog_inventory([RECORD, second_digest])
    assert set(tmp_path.iterdir()) == before
    encoded = inventory_bytes([RECORD, second_digest])
    with pytest.raises(VersionCatalogInventoryFormatError):
        decode_version_catalog_inventory(encoded, archive)
    digest = publish_bytes(archive, encoded)
    with pytest.raises(VersionCatalogInventoryCorruptError):
        archive.get_version_catalog_inventory(digest)
    assert archive.get_observation_record(RECORD).version == first


def test_same_ids_and_ranks_across_distinct_keys_are_isolated(tmp_path: Path) -> None:
    archive, first = prepare(tmp_path)
    versions = [first]
    digests = [RECORD]
    for component in ("security_id", "source_id", "observation_id"):
        other = replace(
            receipt(),
            raw=replace(receipt().raw, key=replace(receipt().raw.key, **{component: "other"})),
        )
        digest, supplied = publish_record(archive, other)
        versions.append(supplied)
        digests.append(digest)
    reopened = archive.get_version_catalog_inventory(archive.put_version_catalog_inventory(digests))
    assert len(reopened.records) == 4
    for supplied in versions:
        assert (
            reopened.to_catalog().latest_usable_at(
                supplied.key, datetime(2025, 1, 3, 11, tzinfo=UTC)
            )
            == supplied
        )
    assert (
        reopened.to_catalog().latest_usable_at(
            ObservationKey("missing", "vendor-a", "release-2025-01-03"),
            datetime(2026, 1, 1, tzinfo=UTC),
        )
        is None
    )


def test_reopened_catalog_preserves_boundaries_ties_and_historical_backfill(tmp_path: Path) -> None:
    archive, first = prepare(tmp_path)
    tied_digest, tied = publish_record(
        archive, replace(receipt(), raw=replace(receipt().raw, version_id="tie")), 1
    )
    later_digest, later = publish_record(archive, changed_release("v2", 4), 2)
    digest = archive.put_version_catalog_inventory([later_digest, RECORD, tied_digest])
    selector = archive.get_version_catalog_inventory(digest).to_catalog()
    assert (
        selector.latest_usable_at(first.key, datetime(2025, 1, 3, 10, 59, 59, 999999, tzinfo=UTC))
        is None
    )
    assert selector.latest_usable_at(first.key, datetime(2025, 1, 3, 11, tzinfo=UTC)) == tied
    assert (
        selector.latest_usable_at(first.key, datetime(2025, 1, 4, 10, 59, 59, 999999, tzinfo=UTC))
        == tied
    )
    assert selector.latest_usable_at(first.key, datetime(2025, 1, 4, 11, tzinfo=UTC)) == later
    assert first.availability.ingested_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert not later.availability.is_available_to_platform_at(
        datetime(2025, 1, 4, 11, tzinfo=UTC), processed_at=datetime(2026, 1, 1, tzinfo=UTC)
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        selector.latest_usable_at(first.key, datetime(2025, 1, 4, 11))


def test_future_member_failure_does_not_yield_an_older_partial_catalog(tmp_path: Path) -> None:
    archive, first = prepare(tmp_path)
    later_digest, _ = publish_record(archive, changed_release("v2", 4), 1)
    inventory_digest = archive.put_version_catalog_inventory([RECORD, later_digest])
    before_later_release = datetime(2025, 1, 3, 11, tzinfo=UTC)
    assert (
        archive.get_version_catalog_inventory(inventory_digest)
        .to_catalog()
        .latest_usable_at(first.key, before_later_release)
        == first
    )
    (tmp_path / later_digest).unlink()
    assert archive.get_observation_record(RECORD).version == first
    with pytest.raises(ObservationRecordMissingError):
        archive.get_version_catalog_inventory(inventory_digest)


def test_direct_inventory_shape_correspondence_and_unverified_dependency_boundary(
    tmp_path: Path,
) -> None:
    archive, _ = prepare(tmp_path)
    original = archive.get_observation_record(RECORD)
    manifest = VersionCatalogManifest([RECORD])
    for invalid_manifest in (None, (), "manifest"):
        with pytest.raises(ValueError, match="VersionCatalogManifest"):
            VersionCatalogInventory(invalid_manifest, (original,))  # type: ignore[arg-type]
    for invalid_records in ([], [original], (None,), (original.version,)):
        with pytest.raises(ValueError, match="immutable tuple"):
            VersionCatalogInventory(manifest, invalid_records)  # type: ignore[arg-type]
    for invalid_records in ((), (original, original)):
        with pytest.raises(ValueError, match="match manifest"):
            VersionCatalogInventory(manifest, invalid_records)
    unsupported = ReceiptLinkedVersion(original.version, "f" * 64)
    with pytest.raises(ValueError, match="match manifest"):
        VersionCatalogInventory(manifest, (unsupported,))
    # A direct object can assert nonexistent dependencies; archive reopen cannot.
    asserted_manifest = VersionCatalogManifest([unsupported.observation_record_sha256])
    asserted = VersionCatalogInventory(asserted_manifest, (unsupported,))
    encoded = encode_version_catalog_inventory(asserted)
    with pytest.raises(ObservationRecordMissingError):
        decode_version_catalog_inventory(encoded, archive)


@pytest.mark.parametrize("invalid", [None, (), [], {}, "inventory"])
def test_encoder_requires_inventory(invalid: Any) -> None:
    with pytest.raises(ValueError, match="VersionCatalogInventory"):
        encode_version_catalog_inventory(invalid)


@pytest.mark.parametrize("invalid", [None, "{}", bytearray(b"{}"), memoryview(b"{}")])
def test_decoder_requires_immutable_bytes(tmp_path: Path, invalid: Any) -> None:
    with pytest.raises(VersionCatalogInventoryFormatError, match="immutable bytes"):
        decode_version_catalog_inventory(invalid, LocalRawArchive(tmp_path))


@pytest.mark.parametrize("invalid", [None, True, b"a" * 64, "A" * 64, "../inventory"])
def test_archive_get_requires_exact_digest(tmp_path: Path, invalid: Any) -> None:
    with pytest.raises(ValueError):
        LocalRawArchive(tmp_path).get_version_catalog_inventory(invalid)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(schema_version=2),
        lambda d: d.update(schema_version=True),
        lambda d: d.update(schema_version=1.0),
        lambda d: d.update(catalog_policy_id="unknown"),
        lambda d: d.update(catalog_policy_id=None),
        lambda d: d.update(extra=None),
        lambda d: d.pop("catalog_policy_id"),
        lambda d: d.update(manifest=[]),
        lambda d: d["manifest"].update(extra=None),
        lambda d: d["manifest"].pop("observation_record_sha256s"),
        lambda d: d["manifest"].update(observation_record_sha256s=RECORD),
        lambda d: d["manifest"].update(observation_record_sha256s=[True]),
        lambda d: d["manifest"].update(observation_record_sha256s=["A" * 64]),
        lambda d: d["manifest"].update(observation_record_sha256s=[RECORD, RECORD]),
    ],
)
def test_rehashed_schema_policy_and_membership_tampering_rejects_before_reads(
    tmp_path: Path, monkeypatch: Any, mutation: Any
) -> None:
    archive, _ = prepare(tmp_path)
    document = json.loads((FIXTURES / "version-catalog-inventory-v1.json").read_bytes())
    mutation(document)
    encoded = canonical(document)
    digest = publish_bytes(archive, encoded)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("invalid inventory caused dependency reads")

    monkeypatch.setattr(archive, "get_observation_record", forbidden)
    with pytest.raises(VersionCatalogInventoryFormatError):
        decode_version_catalog_inventory(encoded, archive)
    with pytest.raises(VersionCatalogInventoryCorruptError):
        archive.get_version_catalog_inventory(digest)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b + b"\n",
        lambda b: b" " + b,
        lambda b: json.dumps(json.loads(b), indent=2).encode("ascii"),
        lambda b: b.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
        lambda b: b.replace(
            b'"observation_record_sha256s":',
            b'"observation_record_sha256s":[],"observation_record_sha256s":',
        ),
        lambda b: b.replace(b'"schema_version":1', b'"schema_version":NaN'),
        lambda b: b.replace(b'"schema_version":1', b'"schema_version":Infinity'),
        lambda b: b"[]",
        lambda b: b"\xff",
    ],
)
def test_duplicate_noncanonical_and_invalid_json_rejects_before_reads(
    tmp_path: Path, monkeypatch: Any, mutate: Any
) -> None:
    archive = LocalRawArchive(tmp_path)
    encoded = mutate((FIXTURES / "version-catalog-inventory-v1.json").read_bytes())

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("noncanonical inventory caused dependency reads")

    monkeypatch.setattr(archive, "get_observation_record", forbidden)
    with pytest.raises(VersionCatalogInventoryFormatError):
        decode_version_catalog_inventory(encoded, archive)


def test_unsorted_membership_and_record_order_cannot_change_manifest_meaning(
    tmp_path: Path, monkeypatch: Any
) -> None:
    archive, _ = prepare(tmp_path)
    other_digest, _ = publish_record(archive, changed_release("v2", 4), 1)
    inventory = build_version_catalog_inventory(archive, [RECORD, other_digest])
    with pytest.raises(ValueError, match="match manifest"):
        VersionCatalogInventory(inventory.manifest, tuple(reversed(inventory.records)))
    document = json.loads(encode_version_catalog_inventory(inventory))
    document["manifest"]["observation_record_sha256s"].reverse()

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("unsorted inventory caused dependency reads")

    monkeypatch.setattr(archive, "get_observation_record", forbidden)
    with pytest.raises(VersionCatalogInventoryFormatError, match="not canonical"):
        decode_version_catalog_inventory(canonical(document), archive)


@pytest.mark.parametrize("digest", [RECEIPT, ABC])
def test_raw_receipt_or_payload_cannot_enter_inventory(tmp_path: Path, digest: str) -> None:
    archive, _ = prepare(tmp_path)
    with pytest.raises(ObservationRecordCorruptError):
        archive.put_version_catalog_inventory([digest])


@pytest.mark.parametrize(
    "target,error",
    [
        ("inventory", VersionCatalogInventoryMissingError),
        ("record", ObservationRecordMissingError),
        ("receipt", ReceiptMissingError),
        ("payload", PayloadMissingError),
    ],
)
def test_missing_selected_object_never_returns_partial_or_fallback(
    tmp_path: Path, target: str, error: type[Exception]
) -> None:
    archive, _ = prepare(tmp_path)
    assert archive.put_version_catalog_inventory([RECORD]) == INVENTORY
    path = (
        tmp_path
        / {"inventory": INVENTORY, "record": RECORD, "receipt": RECEIPT, "payload": ABC}[target]
    )
    path.unlink()
    with pytest.raises(error):
        archive.get_version_catalog_inventory(INVENTORY)
    if target != "inventory":
        before = set(tmp_path.iterdir())
        with pytest.raises(error):
            archive.put_version_catalog_inventory([RECORD])
        assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize(
    "target,error",
    [
        ("inventory", VersionCatalogInventoryCorruptError),
        ("record", ObservationRecordCorruptError),
        ("receipt", ReceiptCorruptError),
        ("payload", PayloadCorruptError),
    ],
)
def test_corrupt_selected_object_is_never_repaired(
    tmp_path: Path, target: str, error: type[Exception]
) -> None:
    archive, _ = prepare(tmp_path)
    assert archive.put_version_catalog_inventory([RECORD]) == INVENTORY
    path = (
        tmp_path
        / {"inventory": INVENTORY, "record": RECORD, "receipt": RECEIPT, "payload": ABC}[target]
    )
    path.chmod(0o600)
    path.write_bytes(b"corrupt")
    with pytest.raises(error):
        archive.get_version_catalog_inventory(INVENTORY)
    with pytest.raises(PayloadCorruptError if target == "inventory" else error):
        archive.put_version_catalog_inventory([RECORD])
    assert path.read_bytes() == b"corrupt"


@pytest.mark.parametrize("kind", ["directory", "symlink", "fifo"])
def test_nonregular_inventory_rejects_without_following_or_blocking(
    tmp_path: Path, kind: str
) -> None:
    archive, _ = prepare(tmp_path)
    path = tmp_path / INVENTORY
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        path.symlink_to(tmp_path / RECORD)
    else:
        os.mkfifo(path)
    with pytest.raises(VersionCatalogInventoryCorruptError):
        archive.get_version_catalog_inventory(INVENTORY)
    assert archive.get_observation_record(RECORD).receipt_sha256 == RECEIPT


def test_all_dependencies_verify_before_any_inventory_publication(
    tmp_path: Path, monkeypatch: Any
) -> None:
    archive, _ = prepare(tmp_path)
    before = set(tmp_path.iterdir())

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("inventory publication attempted before dependency verification")

    monkeypatch.setattr(archive, "put", forbidden)
    with pytest.raises(ObservationRecordMissingError):
        archive.put_version_catalog_inventory([RECORD, "f" * 64])
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize("failure", ["create", "write", "file_close", "verify", "link"])
def test_prepublication_failure_exposes_no_inventory(
    tmp_path: Path, monkeypatch: Any, failure: str
) -> None:
    archive, _ = prepare(tmp_path)
    real_open, real_close, real_read = os.open, os.close, LocalRawArchive._read
    expected_size = len((FIXTURES / "version-catalog-inventory-v1.json").read_bytes())

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise OSError(errno.EIO, "injected inventory publication failure")

    def fail_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        return fail() if flags & os.O_CREAT else real_open(path, flags, *args, **kwargs)

    def fail_close(descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        is_inventory = stat.S_ISREG(metadata.st_mode) and metadata.st_size == expected_size
        real_close(descriptor)
        if is_inventory:
            fail()

    def fail_verify(directory: int, name: str, digest: str) -> bytes:
        if name.startswith(".staging-") and digest == INVENTORY:
            raise PayloadCorruptError("injected staged inventory verification failure")
        return real_read(directory, name, digest)

    if failure == "create":
        monkeypatch.setattr(raw_archive.os, "open", fail_open)
    elif failure == "write":
        monkeypatch.setattr(raw_archive.os, "write", fail)
    elif failure == "file_close":
        monkeypatch.setattr(raw_archive.os, "close", fail_close)
    elif failure == "verify":
        monkeypatch.setattr(LocalRawArchive, "_read", staticmethod(fail_verify))
    else:
        monkeypatch.setattr(raw_archive.os, "link", fail)
    with pytest.raises(PayloadCorruptError if failure == "verify" else ArchiveIOError):
        archive.put_version_catalog_inventory([RECORD])
    assert not (tmp_path / INVENTORY).exists()
    assert archive.get_observation_record(RECORD).receipt_sha256 == RECEIPT


@pytest.mark.parametrize("failure", ["cleanup", "directory_close"])
def test_postpublication_failure_keeps_complete_inventory_and_retry_verifies(
    tmp_path: Path, monkeypatch: Any, failure: str
) -> None:
    archive, _ = prepare(tmp_path)
    real_close = os.close

    def fail_cleanup(*args: Any, **kwargs: Any) -> None:
        raise OSError(errno.EIO, "injected inventory cleanup failure")

    def fail_close(descriptor: int) -> None:
        is_directory = (tmp_path / INVENTORY).exists() and stat.S_ISDIR(
            os.fstat(descriptor).st_mode
        )
        real_close(descriptor)
        if is_directory:
            raise OSError(errno.EIO, "injected inventory directory-close failure")

    with monkeypatch.context() as patch:
        patch.setattr(
            raw_archive.os,
            "unlink" if failure == "cleanup" else "close",
            fail_cleanup if failure == "cleanup" else fail_close,
        )
        with pytest.raises(ArchiveIOError):
            archive.put_version_catalog_inventory([RECORD])
    assert (tmp_path / INVENTORY).read_bytes() == (
        FIXTURES / "version-catalog-inventory-v1.json"
    ).read_bytes()
    assert len(archive.get_version_catalog_inventory(INVENTORY).records) == 1
    assert archive.put_version_catalog_inventory([RECORD]) == INVENTORY
    assert len(list(tmp_path.glob(".staging-*"))) == (1 if failure == "cleanup" else 0)


def test_dependency_filesystem_error_keeps_original_type(tmp_path: Path, monkeypatch: Any) -> None:
    archive, _ = prepare(tmp_path)
    assert archive.put_version_catalog_inventory([RECORD]) == INVENTORY

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise ArchiveIOError("injected record dependency I/O failure")

    monkeypatch.setattr(archive, "get_observation_record", fail)
    with pytest.raises(ArchiveIOError, match="record dependency"):
        archive.get_version_catalog_inventory(INVENTORY)
    with pytest.raises(ArchiveIOError, match="record dependency"):
        archive.put_version_catalog_inventory([RECORD])
