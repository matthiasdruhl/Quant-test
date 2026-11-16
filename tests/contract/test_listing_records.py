"""Independent listing assertion bytes, temporal references and archive failures."""

import errno
import hashlib
import json
import os
import stat
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from quant_test.core.time import InformationAvailability
from quant_test.data import raw_archive
from quant_test.data.admission import AcceptedAvailability
from quant_test.data.listing_records import (
    ListingHistoryRecord,
    ListingHistoryRecordFormatError,
    build_listing_history_record,
    decode_listing_history_record,
    encode_listing_history_record,
)
from quant_test.data.listings import ListingCatalog, ListingHistory, ListingInterval
from quant_test.data.observation_records import ReceiptLinkedVersion
from quant_test.data.raw_archive import (
    ArchiveIOError,
    ListingHistoryRecordCorruptError,
    ListingHistoryRecordMissingError,
    LocalRawArchive,
    ObservationRecordCorruptError,
    ObservationRecordMissingError,
    PayloadCorruptError,
    PayloadMissingError,
    ReceiptCorruptError,
    ReceiptMissingError,
)
from quant_test.data.receipts import AdmissionReceipt, decode_receipt
from quant_test.data.versions import ObservationKey, ObservationVersion

ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
RECEIPT = "620e2e9d81ece91590e1a66d1a8e9e933edba76eb1b422a68f0441f848396011"
METADATA = "e12a322781e5344136f36db81e55ce679b03e754b35db4a33442d81d39af3ac7"
LISTING = "75458f1ed9c9881c187dd5bde8be1516bad05ace7a5ceb2f0f849f4fcfd7734e"
FIXTURES = Path(__file__).parents[1] / "fixtures"
SOURCE = "listing-reference"


def receipt() -> AdmissionReceipt:
    return decode_receipt((FIXTURES / "listing-receipt-v1.json").read_bytes())


def version() -> ObservationVersion:
    return ObservationVersion(
        ObservationKey("security-1", SOURCE, "listing-history"),
        "listing-v1",
        0,
        InformationAvailability(
            None,
            datetime(2025, 1, 3, 10, tzinfo=UTC),
            datetime(2025, 1, 3, 11, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        ),
        " https://listing-source.example/history?v=1 ",
        " reference-listing-license ",
        ABC,
        False,
    )


def history() -> ListingHistory:
    return ListingHistory(
        version(),
        (
            ListingInterval(
                "issuer-1",
                "OLD",
                "XNYS",
                "USD",
                datetime(2020, 1, 1, tzinfo=UTC),
                datetime(2021, 1, 1, tzinfo=UTC),
                "symbol_changed",
            ),
            ListingInterval(
                "issuer-1",
                "NEW",
                "XNYS",
                "USD",
                datetime(2021, 1, 1, tzinfo=UTC),
                datetime(2022, 1, 1, tzinfo=UTC),
                "delisted",
            ),
        ),
    )


def prepare(tmp_path: Path) -> LocalRawArchive:
    archive = LocalRawArchive(tmp_path)
    assert archive.put_receipt(receipt(), b"abc") == RECEIPT
    assert archive.put_observation_record(version(), RECEIPT) == METADATA
    return archive


def publish_history(
    archive: LocalRawArchive, supplied_history: ListingHistory, supplied_receipt: AdmissionReceipt
) -> str:
    receipt_digest = archive.put_receipt(supplied_receipt, b"abc")
    metadata_digest = archive.put_observation_record(supplied_history.version, receipt_digest)
    return archive.put_listing_history_record(supplied_history, metadata_digest)


def revised_history(
    version_id: str, rank: int, day: int, intervals: tuple[ListingInterval, ...]
) -> tuple[ListingHistory, AdmissionReceipt]:
    raw = receipt().raw
    revised_receipt = replace(
        receipt(),
        raw=replace(
            raw,
            version_id=version_id,
            published_at=replace(
                raw.published_at, parsed_value=datetime(2025, 1, day, 10, tzinfo=UTC)
            ),
            source_available_at=replace(
                raw.source_available_at, parsed_value=datetime(2025, 1, day, 11, tzinfo=UTC)
            ),
        ),
    )
    assert isinstance(revised_receipt.result, AcceptedAvailability)
    supplied = replace(
        version(),
        version_id=version_id,
        revision_rank=rank,
        availability=revised_receipt.result.availability,
    )
    return ListingHistory(supplied, intervals), revised_receipt


def canonical(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def publish_bytes(archive: LocalRawArchive, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    archive.put(digest, payload)
    return digest


def test_independent_literal_dependency_chain_and_reopen(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    for name, digest in (
        ("listing-receipt-v1.json", RECEIPT),
        ("listing-observation-record-v1.json", METADATA),
        ("listing-history-record-v1.json", LISTING),
    ):
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == digest
    assert archive.get(METADATA) == (FIXTURES / "listing-observation-record-v1.json").read_bytes()
    supplied = history()
    record = build_listing_history_record(archive, supplied, METADATA)
    expected = (FIXTURES / "listing-history-record-v1.json").read_bytes()
    assert encode_listing_history_record(record) == expected
    assert record.listing_history_record_sha256 == LISTING
    assert record.observation_record_sha256 == METADATA
    assert record.observation_record.receipt_sha256 == RECEIPT
    assert record.history == supplied
    assert record.history is not supplied
    assert archive.put_listing_history_record(supplied, METADATA) == LISTING
    assert archive.put_listing_history_record(supplied, METADATA) == LISTING
    assert LocalRawArchive(tmp_path).get_listing_history_record(LISTING) == record
    assert decode_listing_history_record(expected, archive) == record
    assert {path.name for path in tmp_path.iterdir()} == {ABC, RECEIPT, METADATA, LISTING}
    with pytest.raises(FrozenInstanceError):
        record.history = supplied  # type: ignore[misc]


def test_reopened_rename_delist_and_negative_selected_provenance(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    loaded = archive.get_listing_history_record(
        archive.put_listing_history_record(history(), METADATA)
    )
    catalog = ListingCatalog([loaded.history])
    before = datetime(2025, 1, 3, 10, 59, 59, 999999, tzinfo=UTC)
    known = datetime(2025, 1, 3, 11, tzinfo=UTC)
    assert (
        catalog.listing_at(
            "security-1", SOURCE, "XNYS", datetime(2020, 1, 1, tzinfo=UTC), before
        ).selected_versions
        == ()
    )
    initial = catalog.listing_at(
        "security-1", SOURCE, "XNYS", datetime(2020, 1, 1, tzinfo=UTC), known
    )
    assert initial.match is not None and initial.match.interval.symbol == "OLD"
    renamed = catalog.listing_at(
        "security-1", SOURCE, "XNYS", datetime(2021, 1, 1, tzinfo=UTC), known
    )
    assert renamed.match is not None and renamed.match.interval.symbol == "NEW"
    assert renamed.match.version == version()
    delisted = catalog.listing_at(
        "security-1", SOURCE, "XNYS", datetime(2022, 1, 1, tzinfo=UTC), known
    )
    assert delisted.match is None
    assert delisted.selected_versions == (version(),)
    before_initial = catalog.listing_at(
        "security-1", SOURCE, "XNYS", datetime(2019, 12, 31, tzinfo=UTC), known
    )
    assert before_initial.match is None and before_initial.selected_versions == (version(),)
    assert (
        catalog.resolve_symbol_at(
            "OLD", SOURCE, "XNYS", datetime(2020, 12, 31, tzinfo=UTC), known
        ).match
        == initial.match
    )


def test_reopened_late_correction_and_empty_replacement_do_not_fall_back(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    original = archive.get_listing_history_record(
        archive.put_listing_history_record(history(), METADATA)
    ).history
    corrected_intervals = (
        history().intervals[0],
        replace(history().intervals[1], effective_until=datetime(2021, 12, 1, tzinfo=UTC)),
    )
    corrected, corrected_receipt = revised_history("listing-v2", 1, 4, corrected_intervals)
    second = archive.get_listing_history_record(
        publish_history(archive, corrected, corrected_receipt)
    ).history
    empty, empty_receipt = revised_history("listing-v3", 2, 5, ())
    third = archive.get_listing_history_record(
        publish_history(archive, empty, empty_receipt)
    ).history
    catalog = ListingCatalog([third, second, original])
    effective = datetime(2021, 12, 15, tzinfo=UTC)
    earlier = catalog.listing_at(
        "security-1", SOURCE, "XNYS", effective, datetime(2025, 1, 4, 10, 59, 59, tzinfo=UTC)
    )
    assert earlier.match is not None and earlier.match.version == original.version
    later = catalog.listing_at(
        "security-1", SOURCE, "XNYS", effective, datetime(2025, 1, 4, 11, tzinfo=UTC)
    )
    assert later.match is None and later.selected_versions == (second.version,)
    removed = catalog.listing_at(
        "security-1",
        SOURCE,
        "XNYS",
        datetime(2020, 6, 1, tzinfo=UTC),
        datetime(2025, 1, 5, 11, tzinfo=UTC),
    )
    assert removed.match is None and removed.selected_versions == (third.version,)
    assert third.intervals == ()
    assert original.intervals == history().intervals


def test_reopened_multi_venue_and_ticker_reuse_preserve_stable_ids(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    secondary = ListingInterval(
        "issuer-1",
        "OTHER",
        "XNAS",
        "USD",
        datetime(2020, 1, 1, tzinfo=UTC),
        datetime(2022, 1, 1, tzinfo=UTC),
        "delisted",
    )
    multi = ListingHistory(version(), history().intervals + (secondary,))
    first = archive.get_listing_history_record(
        archive.put_listing_history_record(multi, METADATA)
    ).history
    other_receipt = replace(
        receipt(),
        raw=replace(receipt().raw, key=replace(receipt().raw.key, security_id="security-2")),
    )
    other_version = replace(version(), key=other_receipt.raw.key)
    reused = ListingHistory(
        other_version,
        (ListingInterval("issuer-2", "OLD", "XNYS", "USD", datetime(2022, 1, 2, tzinfo=UTC)),),
    )
    second = archive.get_listing_history_record(
        publish_history(archive, reused, other_receipt)
    ).history
    catalog = ListingCatalog([second, first])
    decision = datetime(2025, 1, 3, 11, tzinfo=UTC)
    old_symbol = catalog.resolve_symbol_at(
        "OLD", SOURCE, "XNYS", datetime(2020, 6, 1, tzinfo=UTC), decision
    )
    assert old_symbol.match is not None and old_symbol.match.version.key.security_id == "security-1"
    reused_symbol = catalog.resolve_symbol_at(
        "OLD", SOURCE, "XNYS", datetime(2022, 1, 2, tzinfo=UTC), decision
    )
    assert (
        reused_symbol.match is not None
        and reused_symbol.match.version.key.security_id == "security-2"
    )
    assert (
        catalog.listing_at(
            "security-1", SOURCE, "XNYS", datetime(2022, 1, 2, tzinfo=UTC), decision
        ).match
        is None
    )
    assert (
        catalog.listing_at(
            "security-1", SOURCE, "XNAS", datetime(2021, 6, 1, tzinfo=UTC), decision
        ).match.interval
        == secondary
    )  # type: ignore[union-attr]


def test_interval_order_exact_text_and_valid_changed_assertions_are_preserved(
    tmp_path: Path,
) -> None:
    archive = prepare(tmp_path)
    original = history()
    reversed_history = ListingHistory(version(), tuple(reversed(original.intervals)))
    reversed_digest = archive.put_listing_history_record(reversed_history, METADATA)
    assert reversed_digest != archive.put_listing_history_record(original, METADATA)
    assert (
        archive.get_listing_history_record(reversed_digest).history.intervals
        == reversed_history.intervals
    )
    changed_interval = replace(
        original.intervals[0],
        issuer_id=" issuer-1 ",
        symbol=" OLDµ ",
        venue=" XNYS ",
        currency=" USD ",
        end_reason=" symbol_changed ",
    )
    changed_history = ListingHistory(version(), (changed_interval, original.intervals[1]))
    changed_digest = archive.put_listing_history_record(changed_history, METADATA)
    assert b"\\u00b5" in archive.get(changed_digest)
    assert (
        archive.get_listing_history_record(changed_digest).history.intervals[0] == changed_interval
    )
    # Valid edited intervals are new assertions, not verified source parsing.
    document = json.loads((FIXTURES / "listing-history-record-v1.json").read_bytes())
    document["intervals"][0]["symbol"] = "DIFFERENT"
    rehashed = publish_bytes(archive, canonical(document))
    assert archive.get_listing_history_record(rehashed).history.intervals[0].symbol == "DIFFERENT"
    assert archive.get_listing_history_record(LISTING).history == original


def test_other_valid_metadata_reference_is_new_assertion_not_silent_version_discard(
    tmp_path: Path,
) -> None:
    archive = prepare(tmp_path)
    revised, revised_receipt = revised_history("listing-v2", 1, 4, history().intervals)
    receipt_digest = archive.put_receipt(revised_receipt, b"abc")
    metadata_digest = archive.put_observation_record(revised.version, receipt_digest)
    metadata = archive.get_observation_record(metadata_digest)
    with pytest.raises(ValueError, match="version differs"):
        ListingHistoryRecord(history(), metadata)
    with pytest.raises(ValueError, match="version differs"):
        archive.put_listing_history_record(history(), metadata_digest)
    document = json.loads((FIXTURES / "listing-history-record-v1.json").read_bytes())
    document["observation_record_sha256"] = metadata_digest
    changed = archive.get_listing_history_record(publish_bytes(archive, canonical(document)))
    assert changed.history.version == revised.version
    assert changed.history.intervals == history().intervals


@pytest.mark.parametrize("component", ["security_id", "source_id"])
def test_each_supplied_key_component_matches_metadata(tmp_path: Path, component: str) -> None:
    archive = prepare(tmp_path)
    supplied = ListingHistory(
        replace(version(), key=replace(version().key, **{component: "different"})),
        history().intervals,
    )
    with pytest.raises(ValueError, match="version differs"):
        archive.put_listing_history_record(supplied, METADATA)


@pytest.mark.parametrize(
    "field,value",
    [
        ("version_id", "other"),
        ("revision_rank", 1),
        ("source_uri", "https://listing-source.example/history?v=1"),
        ("license_id", "reference-listing-license"),
        ("content_sha256", "f" * 64),
    ],
)
def test_each_supplied_version_assertion_matches_metadata(
    tmp_path: Path, field: str, value: Any
) -> None:
    archive = prepare(tmp_path)
    supplied = ListingHistory(replace(version(), **{field: value}), history().intervals)
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError, match="version differs"):
        archive.put_listing_history_record(supplied, METADATA)
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize(
    "field", ["event_at", "published_at", "source_available_at", "ingested_at"]
)
def test_each_supplied_version_time_matches_metadata(tmp_path: Path, field: str) -> None:
    archive = prepare(tmp_path)
    old = getattr(version().availability, field)
    changed = datetime(2020, 1, 1, tzinfo=UTC) if old is None else old + timedelta(microseconds=1)
    supplied = ListingHistory(
        replace(version(), availability=replace(version().availability, **{field: changed})),
        history().intervals,
    )
    with pytest.raises(ValueError, match="version differs"):
        archive.put_listing_history_record(supplied, METADATA)


def test_fixed_listing_history_key_and_metadata_context_are_required(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    general_receipt = decode_receipt((FIXTURES / "admission-receipt-v1.json").read_bytes())
    assert isinstance(general_receipt.result, AcceptedAvailability)
    general_version = ObservationVersion(
        general_receipt.raw.key,
        general_receipt.raw.version_id,
        0,
        general_receipt.result.availability,
        general_receipt.source_uri,
        general_receipt.license_id,
        general_receipt.content_sha256,
        False,
    )
    general_receipt_digest = archive.put_receipt(general_receipt, b"abc")
    general_metadata = archive.put_observation_record(general_version, general_receipt_digest)
    with pytest.raises(ValueError, match="observation_id must be listing-history"):
        ListingHistory(general_version, ())
    with pytest.raises(ValueError, match="version differs"):
        archive.put_listing_history_record(history(), general_metadata)
    document = json.loads((FIXTURES / "listing-history-record-v1.json").read_bytes())
    document["observation_record_sha256"] = general_metadata
    with pytest.raises(ListingHistoryRecordFormatError):
        decode_listing_history_record(canonical(document), archive)


def test_equivalent_metadata_offsets_and_existing_interval_normalization(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    offset = timezone(timedelta(hours=5, minutes=30))
    original = version().availability
    availability = replace(
        original,
        published_at=original.published_at.astimezone(offset),
        source_available_at=original.source_available_at.astimezone(offset),
        ingested_at=original.ingested_at.astimezone(offset),
    )
    intervals = tuple(
        replace(
            item,
            effective_from=item.effective_from.astimezone(offset),
            effective_until=item.effective_until.astimezone(offset),
        )
        for item in history().intervals
    )  # type: ignore[union-attr]
    supplied = ListingHistory(replace(version(), availability=availability), intervals)
    assert archive.put_listing_history_record(supplied, METADATA) == LISTING
    loaded = archive.get_listing_history_record(LISTING)
    assert loaded.history.version.availability.published_at.tzinfo is UTC
    assert loaded.history.intervals == history().intervals


def test_existing_dst_interval_semantics_survive_persistence(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    zone = ZoneInfo("America/New_York")
    interval = ListingInterval(
        "issuer",
        "FOLD",
        "XNYS",
        "USD",
        datetime(2024, 11, 3, 1, 15, tzinfo=zone, fold=0),
        datetime(2024, 11, 3, 1, 45, tzinfo=zone, fold=1),
        "ended",
    )
    assert interval.effective_from == datetime(2024, 11, 3, 5, 15, tzinfo=UTC)
    assert interval.effective_until == datetime(2024, 11, 3, 6, 45, tzinfo=UTC)
    loaded = archive.get_listing_history_record(
        archive.put_listing_history_record(ListingHistory(version(), (interval,)), METADATA)
    )
    assert loaded.history.intervals == (interval,)
    with pytest.raises(ValueError, match="nonexistent"):
        ListingInterval("issuer", "GAP", "XNYS", "USD", datetime(2024, 3, 10, 2, 30, tzinfo=zone))


def test_utc_endpoint_fold_representation_normalizes_without_mutating_input(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    folded = replace(
        history().intervals[0], effective_from=datetime(2020, 1, 1, tzinfo=UTC, fold=1)
    )
    supplied = ListingHistory(version(), (folded, history().intervals[1]))
    assert supplied.intervals[0].effective_from.fold == 1
    assert archive.put_listing_history_record(supplied, METADATA) == LISTING
    assert archive.get_listing_history_record(LISTING).history.intervals[0].effective_from.fold == 0
    assert supplied.intervals[0].effective_from.fold == 1


@pytest.mark.parametrize("digest", [RECEIPT, ABC])
def test_raw_receipt_or_payload_is_not_a_listing_metadata_dependency(
    tmp_path: Path, digest: str
) -> None:
    archive = prepare(tmp_path)
    with pytest.raises(ObservationRecordCorruptError):
        archive.put_listing_history_record(history(), digest)


class DatetimeSubclass(datetime):
    pass


def test_endpoint_subclasses_reject_only_at_new_persistence_boundary(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    endpoint = DatetimeSubclass(2020, 1, 1, tzinfo=UTC)
    interval = ListingInterval("issuer", "A", "XNYS", "USD", endpoint)
    assert type(interval.effective_from) is DatetimeSubclass
    supplied = ListingHistory(version(), (interval,))
    with pytest.raises(ValueError, match="standard UTC"):
        archive.put_listing_history_record(supplied, METADATA)


@pytest.mark.parametrize("invalid", [None, "history", (), [], {}, receipt(), version()])
def test_explicit_history_type_is_required_before_dependency_reads(
    tmp_path: Path, monkeypatch: Any, invalid: Any
) -> None:
    archive = LocalRawArchive(tmp_path)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("invalid history caused dependency read")

    monkeypatch.setattr(archive, "get_observation_record", forbidden)
    with pytest.raises(ValueError, match="ListingHistory"):
        build_listing_history_record(archive, invalid, METADATA)


@pytest.mark.parametrize("invalid", [None, "archive", {}, object()])
def test_empty_history_still_requires_archive(invalid: Any) -> None:
    with pytest.raises(ValueError, match="LocalRawArchive"):
        build_listing_history_record(invalid, ListingHistory(version(), ()), METADATA)
    with pytest.raises(ListingHistoryRecordFormatError):
        decode_listing_history_record(
            (FIXTURES / "listing-history-record-v1.json").read_bytes(), invalid
        )


@pytest.mark.parametrize("invalid", [None, "A" * 64, b"a" * 64, "a" * 63, "../object", True])
def test_invalid_digest_rejects_before_dependency_reads(
    tmp_path: Path, monkeypatch: Any, invalid: Any
) -> None:
    archive = LocalRawArchive(tmp_path)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("invalid digest caused dependency read")

    monkeypatch.setattr(archive, "get_observation_record", forbidden)
    with pytest.raises(ValueError):
        archive.put_listing_history_record(history(), invalid)
    with pytest.raises(ValueError):
        archive.get_listing_history_record(invalid)


@pytest.mark.parametrize("invalid", [None, (), [], {}, history()])
def test_encoder_requires_record(invalid: Any) -> None:
    with pytest.raises(ValueError, match="ListingHistoryRecord"):
        encode_listing_history_record(invalid)


@pytest.mark.parametrize("invalid", [None, "{}", bytearray(b"{}"), memoryview(b"{}")])
def test_decoder_requires_immutable_bytes(tmp_path: Path, invalid: Any) -> None:
    with pytest.raises(ListingHistoryRecordFormatError, match="immutable bytes"):
        decode_listing_history_record(invalid, LocalRawArchive(tmp_path))


def test_bare_record_cannot_claim_dependency_existence(tmp_path: Path) -> None:
    archive = LocalRawArchive(tmp_path)
    asserted = ReceiptLinkedVersion(version(), "f" * 64)
    record = ListingHistoryRecord(history(), asserted)
    with pytest.raises(ObservationRecordMissingError):
        decode_listing_history_record(encode_listing_history_record(record), archive)
    with pytest.raises(ValueError, match="ReceiptLinkedVersion"):
        ListingHistoryRecord(history(), None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field,value",
    [
        ("issuer_id", ""),
        ("symbol", " "),
        ("venue", None),
        ("currency", 1),
        ("effective_from", None),
        ("effective_from", "2020-01-01"),
        ("effective_from", "2020-01-01T00:00:00Z"),
        ("effective_from", "2020-01-01T00:00:00.000000+00:00"),
        ("effective_from", "2020-01-01T01:00:00.000000+01:00"),
        ("effective_until", "2020-01-01T00:00:00.000000Z"),
        ("effective_until", "2019-01-01T00:00:00.000000Z"),
        ("effective_until", None),
        ("end_reason", None),
        ("end_reason", " "),
        ("end_reason", False),
    ],
)
def test_rehashed_invalid_interval_fields_reject(tmp_path: Path, field: str, value: Any) -> None:
    archive = prepare(tmp_path)
    document = json.loads((FIXTURES / "listing-history-record-v1.json").read_bytes())
    document["intervals"][0][field] = value
    encoded = canonical(document)
    with pytest.raises(ListingHistoryRecordFormatError):
        decode_listing_history_record(encoded, archive)
    with pytest.raises(ListingHistoryRecordCorruptError):
        archive.get_listing_history_record(publish_bytes(archive, encoded))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(schema_version=2),
        lambda d: d.update(schema_version=True),
        lambda d: d.update(schema_version=1.0),
        lambda d: d.update(listing_policy_id="unknown"),
        lambda d: d.update(extra=None),
        lambda d: d.pop("observation_record_sha256"),
        lambda d: d.update(observation_record_sha256="A" * 64),
        lambda d: d.update(intervals={}),
        lambda d: d.update(intervals=None),
        lambda d: d.update(intervals=""),
        lambda d: d.update(intervals=[True]),
        lambda d: d["intervals"][0].update(extra=None),
        lambda d: d["intervals"][0].pop("currency"),
    ],
)
def test_strict_schema_policy_container_and_field_sets_reject_before_reads(
    tmp_path: Path, monkeypatch: Any, mutation: Any
) -> None:
    archive = LocalRawArchive(tmp_path)
    document = json.loads((FIXTURES / "listing-history-record-v1.json").read_bytes())
    mutation(document)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("malformed listing caused dependency reads")

    monkeypatch.setattr(archive, "get_observation_record", forbidden)
    with pytest.raises(ListingHistoryRecordFormatError):
        decode_listing_history_record(canonical(document), archive)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b + b"\n",
        lambda b: b" " + b,
        lambda b: json.dumps(json.loads(b), indent=2).encode("ascii"),
        lambda b: b.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
        lambda b: b.replace(b'"symbol":"OLD"', b'"symbol":"OLD","symbol":"OLD"'),
        lambda b: b.replace(b'"schema_version":1', b'"schema_version":NaN'),
        lambda b: b.replace(b'"schema_version":1', b'"schema_version":Infinity'),
        lambda b: b"[]",
        lambda b: b"\xff",
    ],
)
def test_duplicate_noncanonical_and_invalid_json_rejects(
    tmp_path: Path, monkeypatch: Any, mutate: Any
) -> None:
    archive = LocalRawArchive(tmp_path)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("noncanonical listing caused dependency reads")

    monkeypatch.setattr(archive, "get_observation_record", forbidden)
    with pytest.raises(ListingHistoryRecordFormatError):
        decode_listing_history_record(
            mutate((FIXTURES / "listing-history-record-v1.json").read_bytes()), archive
        )


def test_duplicate_and_overlapping_intervals_reject_without_changing_old_contract(
    tmp_path: Path,
) -> None:
    archive = prepare(tmp_path)
    document = json.loads((FIXTURES / "listing-history-record-v1.json").read_bytes())
    document["intervals"].append(document["intervals"][0].copy())
    with pytest.raises(ListingHistoryRecordFormatError):
        decode_listing_history_record(canonical(document), archive)
    document["intervals"].pop()
    document["intervals"][1]["effective_from"] = "2020-12-31T00:00:00.000000Z"
    with pytest.raises(ListingHistoryRecordFormatError):
        decode_listing_history_record(canonical(document), archive)
    for invalid in (None, "", {}, set()):
        with pytest.raises(ValueError, match="tuple or list"):
            ListingHistory(version(), invalid)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "target,error",
    [
        ("listing", ListingHistoryRecordMissingError),
        ("metadata", ObservationRecordMissingError),
        ("receipt", ReceiptMissingError),
        ("payload", PayloadMissingError),
    ],
)
def test_missing_objects_fail_without_fallback(
    tmp_path: Path, target: str, error: type[Exception]
) -> None:
    archive = prepare(tmp_path)
    assert archive.put_listing_history_record(history(), METADATA) == LISTING
    (
        tmp_path
        / {"listing": LISTING, "metadata": METADATA, "receipt": RECEIPT, "payload": ABC}[target]
    ).unlink()
    with pytest.raises(error):
        archive.get_listing_history_record(LISTING)
    if target != "listing":
        with pytest.raises(error):
            archive.put_listing_history_record(history(), METADATA)


@pytest.mark.parametrize(
    "target,error",
    [
        ("listing", ListingHistoryRecordCorruptError),
        ("metadata", ObservationRecordCorruptError),
        ("receipt", ReceiptCorruptError),
        ("payload", PayloadCorruptError),
    ],
)
def test_corrupt_objects_are_never_repaired(
    tmp_path: Path, target: str, error: type[Exception]
) -> None:
    archive = prepare(tmp_path)
    assert archive.put_listing_history_record(history(), METADATA) == LISTING
    path = (
        tmp_path
        / {"listing": LISTING, "metadata": METADATA, "receipt": RECEIPT, "payload": ABC}[target]
    )
    path.chmod(0o600)
    path.write_bytes(b"corrupt")
    with pytest.raises(error):
        archive.get_listing_history_record(LISTING)
    with pytest.raises(PayloadCorruptError if target == "listing" else error):
        archive.put_listing_history_record(history(), METADATA)
    assert path.read_bytes() == b"corrupt"


@pytest.mark.parametrize("kind", ["directory", "symlink", "fifo"])
def test_nonregular_listing_objects_reject_without_following_or_blocking(
    tmp_path: Path, kind: str
) -> None:
    archive = prepare(tmp_path)
    path = tmp_path / LISTING
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        path.symlink_to(tmp_path / METADATA)
    else:
        os.mkfifo(path)
    with pytest.raises(ListingHistoryRecordCorruptError):
        archive.get_listing_history_record(LISTING)
    assert archive.get_observation_record(METADATA).version == version()


def test_dependency_verification_precedes_publication(tmp_path: Path, monkeypatch: Any) -> None:
    archive = prepare(tmp_path)
    (tmp_path / ABC).unlink()

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("listing publication attempted before dependency verification")

    monkeypatch.setattr(archive, "put", forbidden)
    with pytest.raises(PayloadMissingError):
        archive.put_listing_history_record(history(), METADATA)
    assert not (tmp_path / LISTING).exists()


@pytest.mark.parametrize("failure", ["create", "write", "file_close", "verify", "link"])
def test_prepublication_failure_exposes_no_listing_record(
    tmp_path: Path, monkeypatch: Any, failure: str
) -> None:
    archive = prepare(tmp_path)
    real_open, real_close, real_read = os.open, os.close, LocalRawArchive._read
    expected_size = len((FIXTURES / "listing-history-record-v1.json").read_bytes())

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise OSError(errno.EIO, "injected listing publication failure")

    def fail_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        return fail() if flags & os.O_CREAT else real_open(path, flags, *args, **kwargs)

    def fail_close(descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        is_listing = stat.S_ISREG(metadata.st_mode) and metadata.st_size == expected_size
        real_close(descriptor)
        if is_listing:
            fail()

    def fail_verify(directory: int, name: str, digest: str) -> bytes:
        if name.startswith(".staging-") and digest == LISTING:
            raise PayloadCorruptError("injected staged listing verification failure")
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
        archive.put_listing_history_record(history(), METADATA)
    assert not (tmp_path / LISTING).exists()
    assert archive.get_observation_record(METADATA).version == version()


@pytest.mark.parametrize("failure", ["cleanup", "directory_close"])
def test_postpublication_failure_keeps_complete_listing_and_retry_verifies(
    tmp_path: Path, monkeypatch: Any, failure: str
) -> None:
    archive = prepare(tmp_path)
    real_close = os.close

    def fail_cleanup(*args: Any, **kwargs: Any) -> None:
        raise OSError(errno.EIO, "injected listing cleanup failure")

    def fail_close(descriptor: int) -> None:
        is_directory = (tmp_path / LISTING).exists() and stat.S_ISDIR(os.fstat(descriptor).st_mode)
        real_close(descriptor)
        if is_directory:
            raise OSError(errno.EIO, "injected listing directory-close failure")

    with monkeypatch.context() as patch:
        patch.setattr(
            raw_archive.os,
            "unlink" if failure == "cleanup" else "close",
            fail_cleanup if failure == "cleanup" else fail_close,
        )
        with pytest.raises(ArchiveIOError):
            archive.put_listing_history_record(history(), METADATA)
    assert (tmp_path / LISTING).read_bytes() == (
        FIXTURES / "listing-history-record-v1.json"
    ).read_bytes()
    assert archive.get_listing_history_record(LISTING).history == history()
    assert archive.put_listing_history_record(history(), METADATA) == LISTING
    assert len(list(tmp_path.glob(".staging-*"))) == (1 if failure == "cleanup" else 0)


def test_dependency_io_error_keeps_original_type(tmp_path: Path, monkeypatch: Any) -> None:
    archive = prepare(tmp_path)
    assert archive.put_listing_history_record(history(), METADATA) == LISTING

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise ArchiveIOError("injected observation dependency failure")

    monkeypatch.setattr(archive, "get_observation_record", fail)
    with pytest.raises(ArchiveIOError, match="observation dependency"):
        archive.get_listing_history_record(LISTING)
    with pytest.raises(ArchiveIOError, match="observation dependency"):
        archive.put_listing_history_record(history(), METADATA)
