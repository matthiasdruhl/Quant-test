"""Hand-specified receipt-count references and fail-closed archive boundaries."""

import errno
import hashlib
import json
import os
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from quant_test.data import raw_archive
from quant_test.data.admission import RawTimestampClaim, TimestampStatus
from quant_test.data.raw_archive import (
    ArchiveIOError,
    LocalRawArchive,
    PayloadCorruptError,
    PayloadMissingError,
    ReceiptCorruptError,
    ReceiptMissingError,
    ReceiptSetCorruptError,
    ReceiptSetMissingError,
)
from quant_test.data.receipt_sets import (
    ReceiptSetFormatError,
    ReceiptSetManifest,
    build_receipt_set,
    decode_receipt_set,
    encode_receipt_set,
)
from quant_test.data.receipts import AdmissionReceipt, decode_receipt
from quant_test.data.versions import VersionCatalog

ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
REFERENCE_RECEIPT = "7e8aff016576493bff7d2a97733c8fb75cef76c68fafd4f9736dd7e6bda5fb1c"
FIXTURES = Path(__file__).parents[1] / "fixtures"


def reference() -> AdmissionReceipt:
    return decode_receipt((FIXTURES / "admission-receipt-v1.json").read_bytes())


def canonical(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def store_bytes(archive: LocalRawArchive, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    archive.put(digest, payload)
    return digest


def test_independent_canonical_reference_reopen_and_optional_nulls(tmp_path: Path) -> None:
    archive = LocalRawArchive(tmp_path)
    assert archive.put_receipt(reference(), b"abc") == REFERENCE_RECEIPT
    expected = (FIXTURES / "raw-receipt-set-v1.json").read_bytes()
    receipt_set = build_receipt_set(archive, [REFERENCE_RECEIPT])
    assert encode_receipt_set(receipt_set) == expected
    expected_digest = "1bdc0862fd6551059c51b82b850dad176111e8f30eeec79ce3f888804ae35ea6"
    assert hashlib.sha256(expected).hexdigest() == expected_digest
    assert archive.put_receipt_set([REFERENCE_RECEIPT]) == expected_digest
    assert archive.put_receipt_set((REFERENCE_RECEIPT,)) == expected_digest
    assert LocalRawArchive(tmp_path).get_receipt_set(expected_digest) == receipt_set
    assert receipt_set.receipt_set_sha256 == expected_digest
    assert receipt_set.report.receipt_count == receipt_set.report.accepted_count == 1
    assert receipt_set.report.quarantined_count == 0
    assert receipt_set.report.unknown_event_time_count == 1
    assert receipt_set.report.quarantine_reasons == ()
    assert set(path.name for path in tmp_path.iterdir()) == {
        ABC,
        REFERENCE_RECEIPT,
        expected_digest,
    }
    for item in (
        receipt_set,
        receipt_set.manifest,
        receipt_set.report,
        *receipt_set.report.release_fields,
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(item, fields(item)[0].name, None)
    # Optional source_text=None is counted without changing admission.
    record = reference()
    record = replace(
        record,
        raw=replace(record.raw, published_at=replace(record.raw.published_at, source_text=None)),
    )
    digest = archive.put_receipt(record, b"abc")
    report = archive.get_receipt_set(archive.put_receipt_set([digest])).report
    assert report.release_fields[0].source_text_null_count == 1
    assert report.accepted_count == 1
    assert report.quarantined_count == 0
    with pytest.raises(ValueError, match="ObservationVersion"):
        VersionCatalog([receipt_set])  # type: ignore[list-item]


def test_empty_inventory_has_zero_counts_and_explicit_membership(tmp_path: Path) -> None:
    archive = LocalRawArchive(tmp_path)
    # Unmentioned receipts never enter an inventory, even in the same root.
    archive.put_receipt(reference(), b"abc")
    digest = archive.put_receipt_set([])
    result = archive.get_receipt_set(digest)
    assert result.manifest.receipt_sha256s == ()
    assert digest == archive.put_receipt_set(())
    document = json.loads(encode_receipt_set(result))
    report = document["report"]
    assert report["receipt_count"] == report["accepted_count"] == report["quarantined_count"] == 0
    assert report["unknown_event_time_count"] == 0
    assert report["quarantine_reasons"] == []
    for field in report["release_fields"]:
        assert all(
            type(value) is int and value == 0 for key, value in field.items() if key != "field"
        )
    assert set(report) == {
        "receipt_count",
        "accepted_count",
        "quarantined_count",
        "unknown_event_time_count",
        "quarantine_reasons",
        "release_fields",
    }


def test_independent_mixed_counts_identity_order_and_multiple_reasons(tmp_path: Path) -> None:
    archive = LocalRawArchive(tmp_path)
    accepted = reference()
    # Same payload, same observation key/version and different raw assertions
    # remain independent receipt identities; no revision selection is performed.
    second = replace(accepted, source_uri="another-source-assertion")
    unknown = replace(
        accepted,
        raw=replace(
            accepted.raw,
            published_at=RawTimestampClaim(None, None, TimestampStatus.UNKNOWN, None, "no release"),
        ),
    )
    approximate = replace(
        accepted,
        raw=replace(
            accepted.raw,
            published_at=RawTimestampClaim(
                date(2025, 1, 3), "date only", TimestampStatus.APPROXIMATE, "", None
            ),
        ),
    )
    unverified = replace(
        accepted,
        raw=replace(
            accepted.raw,
            event_at=datetime(2025, 1, 2, tzinfo=UTC),
            published_at=RawTimestampClaim(
                datetime(2025, 1, 3), None, TimestampStatus.UNVERIFIED, "evidence", "unproven"
            ),
        ),
    )
    digests = [
        archive.put_receipt(record, b"abc")
        for record in (accepted, second, unknown, approximate, unverified)
    ]
    assert len(set(digests)) == 5
    supplied = list(reversed(digests))
    receipt_set = build_receipt_set(archive, supplied)
    supplied.clear()
    assert receipt_set.manifest.receipt_sha256s == tuple(sorted(digests))
    digest = archive.put_receipt_set(digests)
    assert archive.put_receipt_set(list(reversed(digests))) == digest
    report = archive.get_receipt_set(digest).report
    assert (
        report.receipt_count,
        report.accepted_count,
        report.quarantined_count,
        report.unknown_event_time_count,
    ) == (5, 2, 3, 4)
    published, provider = report.release_fields
    assert (
        published.parsed_value_null_count,
        published.date_only_count,
        published.source_text_null_count,
        published.evidence_reference_null_count,
        published.uncertainty_reason_null_count,
    ) == (1, 1, 2, 1, 3)
    assert (
        published.exact_status_count,
        published.unknown_status_count,
        published.approximate_status_count,
        published.unverified_status_count,
    ) == (2, 1, 1, 1)
    assert (
        provider.parsed_value_null_count,
        provider.date_only_count,
        provider.source_text_null_count,
        provider.evidence_reference_null_count,
        provider.uncertainty_reason_null_count,
        provider.exact_status_count,
    ) == (0, 0, 0, 0, 5, 5)
    actual_reasons = {(item.field, item.reason): item.count for item in report.quarantine_reasons}
    assert actual_reasons == {
        ("published_at", "status is unknown, not exact"): 1,
        ("published_at", "missing or unparsed timestamp"): 1,
        ("published_at", "missing nonblank evidence reference"): 2,
        ("published_at", "timestamp uncertainty is declared"): 2,
        ("published_at", "status is approximate, not exact"): 1,
        ("published_at", "date-only value has no exact release instant"): 1,
        ("published_at", "missing nonblank uncertainty reason"): 1,
        ("published_at", "status is unverified, not exact"): 1,
        ("published_at", "timestamp must be timezone-aware"): 1,
    }
    assert sum(actual_reasons.values()) == 11 > report.quarantined_count


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        "a" * 64,
        b"a" * 64,
        set(),
        {},
        iter([]),
        [REFERENCE_RECEIPT, REFERENCE_RECEIPT],
        [None],
        [True],
        ["A" * 64],
        ["a" * 63],
        [" a" * 32],
    ],
)
def test_invalid_collections_reject_before_access(tmp_path: Path, invalid: Any) -> None:
    archive = LocalRawArchive(tmp_path)
    with pytest.raises(ValueError):
        archive.put_receipt_set(invalid)
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ValueError):
        ReceiptSetManifest(invalid)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(schema_version=True),
        lambda d: d.update(schema_version=2),
        lambda d: d.update(admission_policy_id="future"),
        lambda d: d.update(quality_policy_id="future"),
        lambda d: d.update(extra=0),
        lambda d: d.pop("report"),
        lambda d: d["manifest"].update(extra=0),
        lambda d: d["manifest"].update(receipt_sha256s=None),
        lambda d: d["manifest"]["receipt_sha256s"].append(REFERENCE_RECEIPT),
        lambda d: d["report"].update(receipt_count=2),
        lambda d: d["report"].update(accepted_count=True),
        lambda d: d["report"].update(quarantined_count=-1),
        lambda d: d["report"].update(unknown_event_time_count=0),
        lambda d: d["report"].update(
            quarantine_reasons=[{"field": "x", "reason": "y", "count": 1}]
        ),
        lambda d: d["report"]["release_fields"][0].update(exact_status_count=0),
        lambda d: d["report"]["release_fields"][0].update(source_text_null_count=True),
        lambda d: d["report"]["release_fields"].reverse(),
    ],
)
def test_rehashed_manifest_report_tampering_rejects(tmp_path: Path, mutation: Any) -> None:
    archive = LocalRawArchive(tmp_path)
    archive.put_receipt(reference(), b"abc")
    document = json.loads((FIXTURES / "raw-receipt-set-v1.json").read_bytes())
    mutation(document)
    digest = store_bytes(archive, canonical(document))
    with pytest.raises(ReceiptSetCorruptError):
        archive.get_receipt_set(digest)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p + b"\n",
        lambda p: b" " + p,
        lambda p: p.replace(b'"schema_version":1', b'"schema_version":1.0'),
        lambda p: p.replace(b'"schema_version":1', b'"schema_version":NaN'),
        lambda p: p.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
        lambda p: p.replace(b'"receipt_count":1', b'"receipt_count":1,"receipt_count":1'),
        lambda p: p.replace(b'"date_only_count":0', b'"date_only_count":0,"date_only_count":0', 1),
        lambda p: p.replace(b'"manifest":{', b'"manifest":{ "ignored":null,'),
        lambda p: b"[]",
        lambda p: b"\xff",
    ],
)
def test_noncanonical_or_duplicate_json_rejects(tmp_path: Path, mutate: Any) -> None:
    archive = LocalRawArchive(tmp_path)
    archive.put_receipt(reference(), b"abc")
    encoded = mutate((FIXTURES / "raw-receipt-set-v1.json").read_bytes())
    with pytest.raises(ReceiptSetFormatError):
        decode_receipt_set(encoded, archive)
    with pytest.raises(ReceiptSetCorruptError):
        archive.get_receipt_set(store_bytes(archive, encoded))


@pytest.mark.parametrize(
    "target,error",
    [
        ("receipt", ReceiptMissingError),
        ("payload", PayloadMissingError),
        ("manifest", ReceiptSetMissingError),
    ],
)
def test_missing_selected_objects_fail_without_fallback(
    tmp_path: Path, target: str, error: Any
) -> None:
    archive = LocalRawArchive(tmp_path)
    receipt_digest = archive.put_receipt(reference(), b"abc")
    digest = archive.put_receipt_set([receipt_digest])
    (tmp_path / {"receipt": receipt_digest, "payload": ABC, "manifest": digest}[target]).unlink()
    with pytest.raises(error):
        archive.get_receipt_set(digest)
    if target != "manifest":
        with pytest.raises(error):
            archive.put_receipt_set([receipt_digest])


@pytest.mark.parametrize(
    "target,error",
    [
        ("receipt", ReceiptCorruptError),
        ("payload", PayloadCorruptError),
        ("manifest", ReceiptSetCorruptError),
    ],
)
def test_corrupt_selected_objects_fail_without_repair(
    tmp_path: Path, target: str, error: Any
) -> None:
    archive = LocalRawArchive(tmp_path)
    receipt_digest = archive.put_receipt(reference(), b"abc")
    digest = archive.put_receipt_set([receipt_digest])
    path = tmp_path / {"receipt": receipt_digest, "payload": ABC, "manifest": digest}[target]
    path.chmod(0o600)
    path.write_bytes(b"corrupt")
    with pytest.raises(error):
        archive.get_receipt_set(digest)
    if target != "manifest":
        with pytest.raises(error):
            archive.put_receipt_set([receipt_digest])
    assert path.read_bytes() == b"corrupt"


def test_all_dependencies_verify_before_any_manifest_publication(tmp_path: Path) -> None:
    archive = LocalRawArchive(tmp_path)
    receipt_digest = archive.put_receipt(reference(), b"abc")
    existing = set(tmp_path.iterdir())
    with pytest.raises(ReceiptMissingError):
        archive.put_receipt_set([receipt_digest, "f" * 64])
    assert set(tmp_path.iterdir()) == existing


def test_prepublication_and_postpublication_failures(tmp_path: Path, monkeypatch: Any) -> None:
    archive = LocalRawArchive(tmp_path)
    receipt_digest = archive.put_receipt(reference(), b"abc")
    encoded = encode_receipt_set(build_receipt_set(archive, [receipt_digest]))
    digest = hashlib.sha256(encoded).hexdigest()
    original_link = os.link

    def fail_link(*args: Any, **kwargs: Any) -> None:
        raise OSError(errno.EIO, "injected manifest link failure")

    monkeypatch.setattr(raw_archive.os, "link", fail_link)
    with pytest.raises(ArchiveIOError):
        archive.put_receipt_set([receipt_digest])
    assert not (tmp_path / digest).exists()
    assert archive.get_receipt(receipt_digest) == reference()
    monkeypatch.setattr(raw_archive.os, "link", original_link)
    original_unlink = os.unlink

    def fail_cleanup(*args: Any, **kwargs: Any) -> None:
        raise OSError(errno.EIO, "injected post-publication cleanup failure")

    monkeypatch.setattr(raw_archive.os, "unlink", fail_cleanup)
    with pytest.raises(ArchiveIOError):
        archive.put_receipt_set([receipt_digest])
    assert (tmp_path / digest).read_bytes() == encoded
    assert archive.get_receipt_set(digest).report.receipt_count == 1
    monkeypatch.setattr(raw_archive.os, "unlink", original_unlink)
    assert archive.put_receipt_set([receipt_digest]) == digest
    assert len(list(tmp_path.glob(".staging-*"))) == 1


@pytest.mark.parametrize("archive", [None, object(), "archive"])
def test_invalid_archive_rejects_even_empty_collection(archive: Any) -> None:
    with pytest.raises(ValueError, match="LocalRawArchive"):
        build_receipt_set(archive, [])


def test_exact_field_reason_groups_include_nonrelease_issues(tmp_path: Path) -> None:
    archive = LocalRawArchive(tmp_path)
    record = reference()
    naive = datetime(2025, 1, 3)
    record = replace(
        record,
        raw=replace(
            record.raw,
            published_at=replace(record.raw.published_at, parsed_value=naive),
            source_available_at=replace(record.raw.source_available_at, parsed_value=naive),
            event_at=naive,
            ingested_at=naive,
        ),
    )
    receipt_digest = archive.put_receipt(record, b"abc")
    report = archive.get_receipt_set(archive.put_receipt_set([receipt_digest])).report
    assert report.receipt_count == report.quarantined_count == 1
    assert report.unknown_event_time_count == 0
    assert [(item.field, item.reason, item.count) for item in report.quarantine_reasons] == [
        ("event_at", "timestamp must be timezone-aware", 1),
        ("ingested_at", "timestamp must be timezone-aware", 1),
        ("published_at", "timestamp must be timezone-aware", 1),
        ("source_available_at", "timestamp must be timezone-aware", 1),
    ]
