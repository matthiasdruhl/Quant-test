"""Independent membership bytes, exact universe identities and reopened join cases."""

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
from quant_test.data.listings import ListingCatalog, ListingHistory, ListingInterval
from quant_test.data.membership_records import (
    MembershipHistoryRecord,
    MembershipHistoryRecordFormatError,
    build_membership_history_record,
    decode_membership_history_record,
    encode_membership_history_record,
)
from quant_test.data.observation_records import ReceiptLinkedVersion
from quant_test.data.raw_archive import (
    ArchiveIOError,
    LocalRawArchive,
    MembershipHistoryRecordCorruptError,
    MembershipHistoryRecordMissingError,
    ObservationRecordCorruptError,
    ObservationRecordMissingError,
    PayloadCorruptError,
    PayloadMissingError,
    ReceiptCorruptError,
    ReceiptMissingError,
)
from quant_test.data.receipts import AdmissionReceipt, decode_receipt
from quant_test.data.universes import (
    MembershipHistory,
    MembershipInterval,
    UniverseCatalog,
    membership_observation_id,
)
from quant_test.data.versions import ObservationKey, ObservationVersion

ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
RECEIPT = "6fa893e84548402199a71a31c1852b6cc8291899ecd304100cf02f2bf80dfea1"
METADATA = "a4560cb475bd9e07960e48772bcf1ce99e4a6fd98fee585932613c0e63936002"
MEMBERSHIP = "40967a79c8ff080be9cea2f339f56c4aa45630c0c42a1eb8684dd355e5c01c79"
FIXTURES = Path(__file__).parents[1] / "fixtures"
SOURCE = "membership-reference"
UNIVERSE = " research:large-cap "


def receipt() -> AdmissionReceipt:
    return decode_receipt((FIXTURES / "membership-receipt-v1.json").read_bytes())


def version() -> ObservationVersion:
    return ObservationVersion(
        ObservationKey("security-1", SOURCE, "universe-membership-history: research:large-cap "),
        "membership-v1",
        0,
        InformationAvailability(
            None,
            datetime(2025, 1, 3, 10, tzinfo=UTC),
            datetime(2025, 1, 3, 10, 30, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        ),
        " https://membership-source.example/history?v=1 ",
        " reference-membership-license ",
        ABC,
        False,
    )


def history() -> MembershipHistory:
    return MembershipHistory(
        UNIVERSE,
        version(),
        (
            MembershipInterval(datetime(2020, 1, 1, tzinfo=UTC), datetime(2022, 1, 1, tzinfo=UTC)),
            MembershipInterval(datetime(2023, 1, 1, tzinfo=UTC)),
        ),
    )


def prepare(tmp_path: Path) -> LocalRawArchive:
    archive = LocalRawArchive(tmp_path)
    assert archive.put_receipt(receipt(), b"abc") == RECEIPT
    assert archive.put_observation_record(version(), RECEIPT) == METADATA
    return archive


def publish_history(
    archive: LocalRawArchive, supplied: MembershipHistory, raw: AdmissionReceipt
) -> str:
    receipt_digest = archive.put_receipt(raw, b"abc")
    metadata_digest = archive.put_observation_record(supplied.version, receipt_digest)
    return archive.put_membership_history_record(supplied, metadata_digest)


def revised_history(
    version_id: str, rank: int, day: int, intervals: tuple[MembershipInterval, ...]
) -> tuple[MembershipHistory, AdmissionReceipt]:
    raw = receipt().raw
    revised = replace(
        receipt(),
        raw=replace(
            raw,
            version_id=version_id,
            published_at=replace(
                raw.published_at, parsed_value=datetime(2025, 1, day, 10, tzinfo=UTC)
            ),
            source_available_at=replace(
                raw.source_available_at, parsed_value=datetime(2025, 1, day, 10, 30, tzinfo=UTC)
            ),
        ),
    )
    assert isinstance(revised.result, AcceptedAvailability)
    supplied = replace(
        version(),
        version_id=version_id,
        revision_rank=rank,
        availability=revised.result.availability,
    )
    return MembershipHistory(UNIVERSE, supplied, intervals), revised


def canonical(document: Any) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def publish_bytes(archive: LocalRawArchive, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    archive.put(digest, payload)
    return digest


def reopen_listing_fixture(archive: LocalRawArchive) -> ListingHistory:
    raw = decode_receipt((FIXTURES / "listing-receipt-v1.json").read_bytes())
    assert isinstance(raw.result, AcceptedAvailability)
    supplied = ObservationVersion(
        raw.raw.key,
        raw.raw.version_id,
        0,
        raw.result.availability,
        raw.source_uri,
        raw.license_id,
        raw.content_sha256,
        False,
    )
    receipt_digest = archive.put_receipt(raw, b"abc")
    metadata_digest = archive.put_observation_record(supplied, receipt_digest)
    assert metadata_digest == "e12a322781e5344136f36db81e55ce679b03e754b35db4a33442d81d39af3ac7"
    digest = publish_bytes(archive, (FIXTURES / "listing-history-record-v1.json").read_bytes())
    return archive.get_listing_history_record(digest).history


def publish_listing(
    archive: LocalRawArchive, supplied: ListingHistory, raw: AdmissionReceipt
) -> ListingHistory:
    receipt_digest = archive.put_receipt(raw, b"abc")
    metadata_digest = archive.put_observation_record(supplied.version, receipt_digest)
    digest = archive.put_listing_history_record(supplied, metadata_digest)
    return archive.get_listing_history_record(digest).history


def test_independent_literal_chain_and_exact_universe_reopen(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    for name, digest in (
        ("membership-receipt-v1.json", RECEIPT),
        ("membership-observation-record-v1.json", METADATA),
        ("membership-history-record-v1.json", MEMBERSHIP),
    ):
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == digest
    assert (
        archive.get(METADATA) == (FIXTURES / "membership-observation-record-v1.json").read_bytes()
    )
    supplied = history()
    record = build_membership_history_record(archive, supplied, METADATA)
    expected = (FIXTURES / "membership-history-record-v1.json").read_bytes()
    assert encode_membership_history_record(record) == expected
    assert record.membership_history_record_sha256 == MEMBERSHIP
    assert record.observation_record_sha256 == METADATA
    assert record.observation_record.receipt_sha256 == RECEIPT
    assert record.history == supplied and record.history is not supplied
    assert record.history.universe_id == UNIVERSE
    assert membership_observation_id(UNIVERSE) == "universe-membership-history: research:large-cap "
    assert archive.put_membership_history_record(supplied, METADATA) == MEMBERSHIP
    assert archive.put_membership_history_record(supplied, METADATA) == MEMBERSHIP
    assert LocalRawArchive(tmp_path).get_membership_history_record(MEMBERSHIP) == record
    assert decode_membership_history_record(expected, archive) == record
    assert {path.name for path in tmp_path.iterdir()} == {ABC, RECEIPT, METADATA, MEMBERSHIP}
    assert set(json.loads(expected)["intervals"][0]) == {"effective_from", "effective_until"}
    with pytest.raises(FrozenInstanceError):
        record.history = supplied  # type: ignore[misc]


def test_reopened_entry_exit_and_reentry_boundaries_keep_negative_provenance(
    tmp_path: Path,
) -> None:
    archive = prepare(tmp_path)
    loaded = archive.get_membership_history_record(
        archive.put_membership_history_record(history(), METADATA)
    ).history
    catalog = UniverseCatalog([loaded])
    known = datetime(2025, 1, 3, 10, 30, tzinfo=UTC)
    before = datetime(2025, 1, 3, 10, 29, 59, 999999, tzinfo=UTC)
    assert (
        catalog.members_at(
            UNIVERSE, SOURCE, datetime(2020, 1, 1, tzinfo=UTC), before
        ).selected_versions
        == ()
    )
    assert catalog.members_at(
        UNIVERSE, SOURCE, datetime(2020, 1, 1, tzinfo=UTC), known
    ).member_ids == ("security-1",)
    exited = catalog.members_at(UNIVERSE, SOURCE, datetime(2022, 1, 1, tzinfo=UTC), known)
    assert exited.member_ids == () and exited.selected_versions == (version(),)
    assert catalog.members_at(
        UNIVERSE, SOURCE, datetime(2023, 1, 1, tzinfo=UTC), known
    ).member_ids == ("security-1",)
    absent = catalog.members_at(UNIVERSE, SOURCE, datetime(2019, 1, 1, tzinfo=UTC), known)
    assert absent.member_ids == () and absent.selected_versions == (version(),)
    assert (
        catalog.members_at(
            UNIVERSE.strip(), SOURCE, datetime(2020, 1, 1, tzinfo=UTC), known
        ).selected_versions
        == ()
    )


def test_reopened_late_removal_and_empty_replacement_affect_only_their_key(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    original = archive.get_membership_history_record(
        archive.put_membership_history_record(history(), METADATA)
    ).history
    removed_intervals = (
        history().intervals[0],
        replace(history().intervals[1], effective_until=datetime(2023, 6, 1, tzinfo=UTC)),
    )
    corrected, corrected_raw = revised_history("membership-v2", 1, 4, removed_intervals)
    second = archive.get_membership_history_record(
        publish_history(archive, corrected, corrected_raw)
    ).history
    empty, empty_raw = revised_history("membership-v3", 2, 5, ())
    third = archive.get_membership_history_record(
        publish_history(archive, empty, empty_raw)
    ).history
    other_raw = replace(
        receipt(),
        raw=replace(receipt().raw, key=replace(receipt().raw.key, security_id="security-2")),
    )
    other = MembershipHistory(
        UNIVERSE, replace(version(), key=other_raw.raw.key), history().intervals
    )
    other_loaded = archive.get_membership_history_record(
        publish_history(archive, other, other_raw)
    ).history
    catalog = UniverseCatalog([third, other_loaded, second, original])
    effective = datetime(2023, 7, 1, tzinfo=UTC)
    assert catalog.members_at(
        UNIVERSE, SOURCE, effective, datetime(2025, 1, 4, 10, 29, 59, tzinfo=UTC)
    ).member_ids == ("security-1", "security-2")
    removed = catalog.members_at(
        UNIVERSE, SOURCE, effective, datetime(2025, 1, 4, 10, 30, tzinfo=UTC)
    )
    assert removed.member_ids == ("security-2",)
    assert removed.selected_versions == (second.version, other_loaded.version)
    replaced = catalog.members_at(
        UNIVERSE, SOURCE, datetime(2020, 6, 1, tzinfo=UTC), datetime(2025, 1, 5, 10, 30, tzinfo=UTC)
    )
    assert replaced.member_ids == ("security-2",)
    assert replaced.selected_versions == (third.version, other_loaded.version)
    assert third.intervals == () and original.intervals == history().intervals


def test_exact_source_and_full_universe_suffixes_are_isolated_after_reopen(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    loaded = archive.get_membership_history_record(
        archive.put_membership_history_record(history(), METADATA)
    ).history
    other_universe = " research:large-cap :extra:tail"
    universe_raw = replace(
        receipt(),
        raw=replace(
            receipt().raw,
            key=replace(
                receipt().raw.key, observation_id=membership_observation_id(other_universe)
            ),
        ),
    )
    universe_history = MembershipHistory(
        other_universe, replace(version(), key=universe_raw.raw.key), history().intervals
    )
    second = archive.get_membership_history_record(
        publish_history(archive, universe_history, universe_raw)
    ).history
    source_raw = replace(
        receipt(),
        raw=replace(receipt().raw, key=replace(receipt().raw.key, source_id="other-source")),
    )
    source_history = MembershipHistory(
        UNIVERSE, replace(version(), key=source_raw.raw.key), history().intervals
    )
    third = archive.get_membership_history_record(
        publish_history(archive, source_history, source_raw)
    ).history
    catalog = UniverseCatalog([third, second, loaded])
    effective, decision = datetime(2020, 6, 1, tzinfo=UTC), datetime(2025, 1, 3, 10, 30, tzinfo=UTC)
    assert catalog.members_at(UNIVERSE, SOURCE, effective, decision).selected_versions == (
        loaded.version,
    )
    assert catalog.members_at(other_universe, SOURCE, effective, decision).selected_versions == (
        second.version,
    )
    assert catalog.members_at(UNIVERSE, "other-source", effective, decision).selected_versions == (
        third.version,
    )
    assert (
        catalog.members_at("research:large-cap", SOURCE, effective, decision).selected_versions
        == ()
    )


def test_reopened_join_has_independent_cutoffs_delisted_unresolved_and_no_ticker_rebind(
    tmp_path: Path,
) -> None:
    archive = prepare(tmp_path)
    member = archive.get_membership_history_record(
        archive.put_membership_history_record(history(), METADATA)
    ).history
    listing = reopen_listing_fixture(archive)
    listing_raw = decode_receipt((FIXTURES / "listing-receipt-v1.json").read_bytes())
    reused_raw = replace(
        listing_raw,
        raw=replace(listing_raw.raw, key=replace(listing_raw.raw.key, security_id="security-2")),
    )
    reused = ListingHistory(
        replace(listing.version, key=reused_raw.raw.key),
        (ListingInterval("issuer-2", "NEW", "XNYS", "USD", datetime(2022, 1, 1, tzinfo=UTC)),),
    )
    reused_loaded = publish_listing(archive, reused, reused_raw)
    universe = UniverseCatalog([member])
    listings = ListingCatalog([reused_loaded, listing])
    effective = datetime(2023, 7, 1, tzinfo=UTC)
    before_member = universe.listings_at(
        UNIVERSE,
        SOURCE,
        listings,
        "listing-reference",
        "XNYS",
        effective,
        datetime(2025, 1, 3, 10, 29, tzinfo=UTC),
    )
    assert before_member.membership.member_ids == ()
    before_listing = universe.listings_at(
        UNIVERSE,
        SOURCE,
        listings,
        "listing-reference",
        "XNYS",
        effective,
        datetime(2025, 1, 3, 10, 30, tzinfo=UTC),
    )
    assert before_listing.membership.member_ids == ("security-1",)
    assert before_listing.unresolved_member_ids == ("security-1",)
    assert before_listing.listing_results[0].selected_versions == ()
    after_listing = universe.listings_at(
        UNIVERSE,
        SOURCE,
        listings,
        "listing-reference",
        "XNYS",
        effective,
        datetime(2025, 1, 3, 11, tzinfo=UTC),
    )
    assert after_listing.membership.member_ids == ("security-1",)
    assert after_listing.unresolved_member_ids == ("security-1",)
    assert after_listing.matches == ()
    assert after_listing.listing_results[0].selected_versions == (listing.version,)
    ticker = listings.resolve_symbol_at(
        "NEW", "listing-reference", "XNYS", effective, datetime(2025, 1, 3, 11, tzinfo=UTC)
    )
    assert ticker.match is not None and ticker.match.version.key.security_id == "security-2"
    assert after_listing.membership.decision_at == after_listing.listing_results[0].decision_at
    assert after_listing.membership.effective_at == after_listing.listing_results[0].effective_at
    # A later mapping revision applies its own provider cutoff, not membership's.
    corrected_raw = replace(
        listing_raw,
        raw=replace(
            listing_raw.raw,
            version_id="listing-v2",
            published_at=replace(
                listing_raw.raw.published_at, parsed_value=datetime(2025, 1, 4, 10, tzinfo=UTC)
            ),
            source_available_at=replace(
                listing_raw.raw.source_available_at,
                parsed_value=datetime(2025, 1, 4, 12, tzinfo=UTC),
            ),
        ),
    )
    assert isinstance(corrected_raw.result, AcceptedAvailability)
    corrected_version = replace(
        listing.version,
        version_id="listing-v2",
        revision_rank=1,
        availability=corrected_raw.result.availability,
    )
    corrected = ListingHistory(
        corrected_version,
        listing.intervals
        + (ListingInterval("issuer-1", "RETURN", "XNYS", "USD", datetime(2023, 1, 1, tzinfo=UTC)),),
    )
    corrected_loaded = publish_listing(archive, corrected, corrected_raw)
    later_listings = ListingCatalog([listing, corrected_loaded, reused_loaded])
    earlier_join = universe.listings_at(
        UNIVERSE,
        SOURCE,
        later_listings,
        "listing-reference",
        "XNYS",
        effective,
        datetime(2025, 1, 4, 11, 59, tzinfo=UTC),
    )
    assert earlier_join.unresolved_member_ids == ("security-1",)
    later_join = universe.listings_at(
        UNIVERSE,
        SOURCE,
        later_listings,
        "listing-reference",
        "XNYS",
        effective,
        datetime(2025, 1, 4, 12, tzinfo=UTC),
    )
    assert later_join.unresolved_member_ids == ()
    assert later_join.matches[0].interval.symbol == "RETURN"
    assert later_join.matches[0].version == corrected_version


def test_order_and_valid_interval_or_reference_changes_remain_new_assertions(
    tmp_path: Path,
) -> None:
    archive = prepare(tmp_path)
    assert archive.put_membership_history_record(history(), METADATA) == MEMBERSHIP
    reversed_history = MembershipHistory(UNIVERSE, version(), tuple(reversed(history().intervals)))
    reversed_digest = archive.put_membership_history_record(reversed_history, METADATA)
    assert reversed_digest != MEMBERSHIP
    assert (
        archive.get_membership_history_record(reversed_digest).history.intervals
        == reversed_history.intervals
    )
    document = json.loads((FIXTURES / "membership-history-record-v1.json").read_bytes())
    document["intervals"][0]["effective_until"] = "2021-01-01T00:00:00.000000Z"
    changed = archive.get_membership_history_record(publish_bytes(archive, canonical(document)))
    assert changed.history.intervals[0].effective_until == datetime(2021, 1, 1, tzinfo=UTC)
    revised, revised_raw = revised_history("membership-v2", 1, 4, history().intervals)
    receipt_digest = archive.put_receipt(revised_raw, b"abc")
    metadata_digest = archive.put_observation_record(revised.version, receipt_digest)
    with pytest.raises(ValueError, match="version differs"):
        MembershipHistoryRecord(history(), archive.get_observation_record(metadata_digest))
    document = json.loads((FIXTURES / "membership-history-record-v1.json").read_bytes())
    document["observation_record_sha256"] = metadata_digest
    assert (
        archive.get_membership_history_record(
            publish_bytes(archive, canonical(document))
        ).history.version
        == revised.version
    )


@pytest.mark.parametrize(
    "other_universe", ["research:large-cap", " research:large-cap :other", " Research:large-cap "]
)
def test_universe_changes_must_match_the_entire_pinned_key(
    tmp_path: Path, other_universe: str
) -> None:
    archive = prepare(tmp_path)
    document = json.loads((FIXTURES / "membership-history-record-v1.json").read_bytes())
    document["universe_id"] = other_universe
    with pytest.raises(MembershipHistoryRecordFormatError):
        decode_membership_history_record(canonical(document), archive)
    with pytest.raises(ValueError, match="exact universe_id"):
        MembershipHistory(other_universe, version(), history().intervals)
    other_raw = replace(
        receipt(),
        raw=replace(
            receipt().raw,
            key=replace(
                receipt().raw.key, observation_id=membership_observation_id(other_universe)
            ),
        ),
    )
    other = MembershipHistory(
        other_universe, replace(version(), key=other_raw.raw.key), history().intervals
    )
    with pytest.raises(ValueError, match="version differs"):
        archive.put_membership_history_record(other, METADATA)
    # Jointly changed valid universe+metadata is explicitly a distinct assertion.
    other_digest = publish_history(archive, other, other_raw)
    assert archive.get_membership_history_record(other_digest).history.universe_id == other_universe


@pytest.mark.parametrize("component", ["security_id", "source_id"])
def test_each_supplied_key_component_matches_metadata(tmp_path: Path, component: str) -> None:
    archive = prepare(tmp_path)
    supplied = MembershipHistory(
        UNIVERSE,
        replace(version(), key=replace(version().key, **{component: "other"})),
        history().intervals,
    )
    with pytest.raises(ValueError, match="version differs"):
        archive.put_membership_history_record(supplied, METADATA)


@pytest.mark.parametrize(
    "field,value",
    [
        ("version_id", "other"),
        ("revision_rank", 1),
        ("source_uri", "https://membership-source.example/history?v=1"),
        ("license_id", "reference-membership-license"),
        ("content_sha256", "f" * 64),
    ],
)
def test_supplied_version_assertions_match_metadata(tmp_path: Path, field: str, value: Any) -> None:
    archive = prepare(tmp_path)
    supplied = MembershipHistory(
        UNIVERSE, replace(version(), **{field: value}), history().intervals
    )
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError, match="version differs"):
        archive.put_membership_history_record(supplied, METADATA)
    assert set(tmp_path.iterdir()) == before


@pytest.mark.parametrize(
    "field", ["event_at", "published_at", "source_available_at", "ingested_at"]
)
def test_supplied_version_times_match_metadata(tmp_path: Path, field: str) -> None:
    archive = prepare(tmp_path)
    old = getattr(version().availability, field)
    changed = datetime(2020, 1, 1, tzinfo=UTC) if old is None else old + timedelta(microseconds=1)
    supplied = MembershipHistory(
        UNIVERSE,
        replace(version(), availability=replace(version().availability, **{field: changed})),
        history().intervals,
    )
    with pytest.raises(ValueError, match="version differs"):
        archive.put_membership_history_record(supplied, METADATA)


def test_offsets_and_existing_dst_endpoint_semantics_survive_reopen(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    offset = timezone(timedelta(hours=5, minutes=30))
    old = version().availability
    availability = replace(
        old,
        published_at=old.published_at.astimezone(offset),
        source_available_at=old.source_available_at.astimezone(offset),
        ingested_at=old.ingested_at.astimezone(offset),
    )
    first = history().intervals[0]
    assert first.effective_until is not None
    intervals = (
        MembershipInterval(
            first.effective_from.astimezone(offset), first.effective_until.astimezone(offset)
        ),
        history().intervals[1],
    )
    supplied = MembershipHistory(UNIVERSE, replace(version(), availability=availability), intervals)
    assert archive.put_membership_history_record(supplied, METADATA) == MEMBERSHIP
    zone = ZoneInfo("America/New_York")
    folded = MembershipInterval(
        datetime(2024, 11, 3, 1, 15, tzinfo=zone, fold=0),
        datetime(2024, 11, 3, 1, 45, tzinfo=zone, fold=1),
    )
    assert folded.effective_from == datetime(2024, 11, 3, 5, 15, tzinfo=UTC)
    assert folded.effective_until == datetime(2024, 11, 3, 6, 45, tzinfo=UTC)
    loaded = archive.get_membership_history_record(
        archive.put_membership_history_record(
            MembershipHistory(UNIVERSE, version(), (folded,)), METADATA
        )
    )
    assert loaded.history.intervals == (folded,)
    with pytest.raises(ValueError, match="nonexistent"):
        MembershipInterval(datetime(2024, 3, 10, 2, 30, tzinfo=zone))


class DatetimeSubclass(datetime):
    pass


def test_endpoint_subclass_rejects_at_new_boundary_and_utc_fold_normalizes(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    interval = MembershipInterval(DatetimeSubclass(2020, 1, 1, tzinfo=UTC))
    assert type(interval.effective_from) is DatetimeSubclass
    with pytest.raises(ValueError, match="standard UTC"):
        archive.put_membership_history_record(
            MembershipHistory(UNIVERSE, version(), (interval,)), METADATA
        )
    folded = replace(
        history().intervals[0], effective_from=datetime(2020, 1, 1, tzinfo=UTC, fold=1)
    )
    supplied = MembershipHistory(UNIVERSE, version(), (folded, history().intervals[1]))
    assert archive.put_membership_history_record(supplied, METADATA) == MEMBERSHIP
    assert supplied.intervals[0].effective_from.fold == 1
    assert (
        archive.get_membership_history_record(MEMBERSHIP).history.intervals[0].effective_from.fold
        == 0
    )


@pytest.mark.parametrize("invalid", [None, "history", (), [], {}, receipt(), version()])
def test_history_type_rejects_before_reads(tmp_path: Path, monkeypatch: Any, invalid: Any) -> None:
    archive = LocalRawArchive(tmp_path)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("invalid history caused dependency reads")

    monkeypatch.setattr(archive, "get_observation_record", forbidden)
    with pytest.raises(ValueError, match="MembershipHistory"):
        build_membership_history_record(archive, invalid, METADATA)


@pytest.mark.parametrize("invalid", [None, "archive", {}, object()])
def test_empty_history_requires_archive(invalid: Any) -> None:
    with pytest.raises(ValueError, match="LocalRawArchive"):
        build_membership_history_record(
            invalid, MembershipHistory(UNIVERSE, version(), ()), METADATA
        )
    with pytest.raises(MembershipHistoryRecordFormatError):
        decode_membership_history_record(
            (FIXTURES / "membership-history-record-v1.json").read_bytes(), invalid
        )


@pytest.mark.parametrize("invalid", [None, "A" * 64, b"a" * 64, "a" * 63, "../object", True])
def test_digest_shape_rejects_before_reads(tmp_path: Path, monkeypatch: Any, invalid: Any) -> None:
    archive = LocalRawArchive(tmp_path)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("invalid digest caused dependency reads")

    monkeypatch.setattr(archive, "get_observation_record", forbidden)
    with pytest.raises(ValueError):
        archive.put_membership_history_record(history(), invalid)
    with pytest.raises(ValueError):
        archive.get_membership_history_record(invalid)


@pytest.mark.parametrize("invalid", [None, (), [], {}, history()])
def test_encoder_requires_record(invalid: Any) -> None:
    with pytest.raises(ValueError, match="MembershipHistoryRecord"):
        encode_membership_history_record(invalid)


@pytest.mark.parametrize("invalid", [None, "{}", bytearray(b"{}"), memoryview(b"{}")])
def test_decoder_requires_immutable_bytes(tmp_path: Path, invalid: Any) -> None:
    with pytest.raises(MembershipHistoryRecordFormatError, match="immutable bytes"):
        decode_membership_history_record(invalid, LocalRawArchive(tmp_path))


def test_bare_record_proves_no_dependency_existence_and_raw_objects_are_not_metadata(
    tmp_path: Path,
) -> None:
    archive = prepare(tmp_path)
    asserted = MembershipHistoryRecord(history(), ReceiptLinkedVersion(version(), "f" * 64))
    with pytest.raises(ObservationRecordMissingError):
        decode_membership_history_record(encode_membership_history_record(asserted), archive)
    with pytest.raises(ValueError, match="ReceiptLinkedVersion"):
        MembershipHistoryRecord(history(), None)  # type: ignore[arg-type]
    for digest in (RECEIPT, ABC):
        with pytest.raises(ObservationRecordCorruptError):
            archive.put_membership_history_record(history(), digest)


@pytest.mark.parametrize(
    "field,value",
    [
        ("effective_from", None),
        ("effective_from", "2020-01-01"),
        ("effective_from", "2020-01-01T00:00:00Z"),
        ("effective_from", "2020-01-01T00:00:00.000000+00:00"),
        ("effective_from", "2020-01-01T01:00:00.000000+01:00"),
        ("effective_until", "2020-01-01T00:00:00.000000Z"),
        ("effective_until", "2019-01-01T00:00:00.000000Z"),
        ("effective_until", True),
    ],
)
def test_rehashed_invalid_endpoint_fields_reject(tmp_path: Path, field: str, value: Any) -> None:
    archive = prepare(tmp_path)
    document = json.loads((FIXTURES / "membership-history-record-v1.json").read_bytes())
    document["intervals"][0][field] = value
    encoded = canonical(document)
    with pytest.raises(MembershipHistoryRecordFormatError):
        decode_membership_history_record(encoded, archive)
    with pytest.raises(MembershipHistoryRecordCorruptError):
        archive.get_membership_history_record(publish_bytes(archive, encoded))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(schema_version=2),
        lambda d: d.update(schema_version=True),
        lambda d: d.update(schema_version=1.0),
        lambda d: d.update(membership_policy_id="unknown"),
        lambda d: d.update(extra=None),
        lambda d: d.pop("universe_id"),
        lambda d: d.update(universe_id=None),
        lambda d: d.update(universe_id=""),
        lambda d: d.update(universe_id=" "),
        lambda d: d.update(observation_record_sha256="A" * 64),
        lambda d: d.update(intervals={}),
        lambda d: d.update(intervals=None),
        lambda d: d.update(intervals=""),
        lambda d: d.update(intervals=[True]),
        lambda d: d["intervals"][0].update(end_reason="removed"),
        lambda d: d["intervals"][0].pop("effective_until"),
    ],
)
def test_strict_schema_no_listing_fields_and_invalid_universe_reject_before_reads(
    tmp_path: Path, monkeypatch: Any, mutation: Any
) -> None:
    archive = LocalRawArchive(tmp_path)
    document = json.loads((FIXTURES / "membership-history-record-v1.json").read_bytes())
    mutation(document)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("invalid membership caused dependency reads")

    monkeypatch.setattr(archive, "get_observation_record", forbidden)
    with pytest.raises(MembershipHistoryRecordFormatError):
        decode_membership_history_record(canonical(document), archive)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b + b"\n",
        lambda b: b" " + b,
        lambda b: json.dumps(json.loads(b), indent=2).encode("ascii"),
        lambda b: b.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
        lambda b: b.replace(
            b'"effective_until":null', b'"effective_until":null,"effective_until":null'
        ),
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
        pytest.fail("noncanonical membership caused dependency reads")

    monkeypatch.setattr(archive, "get_observation_record", forbidden)
    with pytest.raises(MembershipHistoryRecordFormatError):
        decode_membership_history_record(
            mutate((FIXTURES / "membership-history-record-v1.json").read_bytes()), archive
        )


def test_overlap_duplicate_and_invalid_replacement_containers_reject(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    document = json.loads((FIXTURES / "membership-history-record-v1.json").read_bytes())
    document["intervals"].append(document["intervals"][0].copy())
    with pytest.raises(MembershipHistoryRecordFormatError):
        decode_membership_history_record(canonical(document), archive)
    document["intervals"].pop()
    document["intervals"][1]["effective_from"] = "2021-01-01T00:00:00.000000Z"
    with pytest.raises(MembershipHistoryRecordFormatError):
        decode_membership_history_record(canonical(document), archive)
    for invalid in (None, "", {}, set()):
        with pytest.raises(ValueError, match="tuple or list"):
            MembershipHistory(UNIVERSE, version(), invalid)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "target,error",
    [
        ("membership", MembershipHistoryRecordMissingError),
        ("metadata", ObservationRecordMissingError),
        ("receipt", ReceiptMissingError),
        ("payload", PayloadMissingError),
    ],
)
def test_missing_objects_fail_without_fallback(
    tmp_path: Path, target: str, error: type[Exception]
) -> None:
    archive = prepare(tmp_path)
    assert archive.put_membership_history_record(history(), METADATA) == MEMBERSHIP
    (
        tmp_path
        / {"membership": MEMBERSHIP, "metadata": METADATA, "receipt": RECEIPT, "payload": ABC}[
            target
        ]
    ).unlink()
    with pytest.raises(error):
        archive.get_membership_history_record(MEMBERSHIP)
    if target != "membership":
        with pytest.raises(error):
            archive.put_membership_history_record(history(), METADATA)


@pytest.mark.parametrize(
    "target,error",
    [
        ("membership", MembershipHistoryRecordCorruptError),
        ("metadata", ObservationRecordCorruptError),
        ("receipt", ReceiptCorruptError),
        ("payload", PayloadCorruptError),
    ],
)
def test_corrupt_objects_never_repair(tmp_path: Path, target: str, error: type[Exception]) -> None:
    archive = prepare(tmp_path)
    assert archive.put_membership_history_record(history(), METADATA) == MEMBERSHIP
    path = (
        tmp_path
        / {"membership": MEMBERSHIP, "metadata": METADATA, "receipt": RECEIPT, "payload": ABC}[
            target
        ]
    )
    path.chmod(0o600)
    path.write_bytes(b"corrupt")
    with pytest.raises(error):
        archive.get_membership_history_record(MEMBERSHIP)
    with pytest.raises(PayloadCorruptError if target == "membership" else error):
        archive.put_membership_history_record(history(), METADATA)
    assert path.read_bytes() == b"corrupt"


@pytest.mark.parametrize("kind", ["directory", "symlink", "fifo"])
def test_nonregular_membership_rejects_without_following_or_blocking(
    tmp_path: Path, kind: str
) -> None:
    archive = prepare(tmp_path)
    path = tmp_path / MEMBERSHIP
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        path.symlink_to(tmp_path / METADATA)
    else:
        os.mkfifo(path)
    with pytest.raises(MembershipHistoryRecordCorruptError):
        archive.get_membership_history_record(MEMBERSHIP)
    assert archive.get_observation_record(METADATA).version == version()


def test_dependency_verification_precedes_publication(tmp_path: Path, monkeypatch: Any) -> None:
    archive = prepare(tmp_path)
    (tmp_path / ABC).unlink()

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("membership publication preceded dependency verification")

    monkeypatch.setattr(archive, "put", forbidden)
    with pytest.raises(PayloadMissingError):
        archive.put_membership_history_record(history(), METADATA)
    assert not (tmp_path / MEMBERSHIP).exists()


@pytest.mark.parametrize("failure", ["create", "write", "file_close", "verify", "link"])
def test_prepublication_failure_exposes_no_membership(
    tmp_path: Path, monkeypatch: Any, failure: str
) -> None:
    archive = prepare(tmp_path)
    real_open, real_close, real_read = os.open, os.close, LocalRawArchive._read
    expected_size = len((FIXTURES / "membership-history-record-v1.json").read_bytes())

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise OSError(errno.EIO, "injected membership publication failure")

    def fail_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        return fail() if flags & os.O_CREAT else real_open(path, flags, *args, **kwargs)

    def fail_close(descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        is_membership = stat.S_ISREG(metadata.st_mode) and metadata.st_size == expected_size
        real_close(descriptor)
        if is_membership:
            fail()

    def fail_verify(directory: int, name: str, digest: str) -> bytes:
        if name.startswith(".staging-") and digest == MEMBERSHIP:
            raise PayloadCorruptError("injected staged membership verification failure")
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
        archive.put_membership_history_record(history(), METADATA)
    assert not (tmp_path / MEMBERSHIP).exists()
    assert archive.get_observation_record(METADATA).version == version()


@pytest.mark.parametrize("failure", ["cleanup", "directory_close"])
def test_postpublication_failure_keeps_complete_membership_and_retry_verifies(
    tmp_path: Path, monkeypatch: Any, failure: str
) -> None:
    archive = prepare(tmp_path)
    real_close = os.close

    def fail_cleanup(*args: Any, **kwargs: Any) -> None:
        raise OSError(errno.EIO, "injected membership cleanup failure")

    def fail_close(descriptor: int) -> None:
        is_directory = (tmp_path / MEMBERSHIP).exists() and stat.S_ISDIR(
            os.fstat(descriptor).st_mode
        )
        real_close(descriptor)
        if is_directory:
            raise OSError(errno.EIO, "injected membership directory-close failure")

    with monkeypatch.context() as patch:
        patch.setattr(
            raw_archive.os,
            "unlink" if failure == "cleanup" else "close",
            fail_cleanup if failure == "cleanup" else fail_close,
        )
        with pytest.raises(ArchiveIOError):
            archive.put_membership_history_record(history(), METADATA)
    assert (tmp_path / MEMBERSHIP).read_bytes() == (
        FIXTURES / "membership-history-record-v1.json"
    ).read_bytes()
    assert archive.get_membership_history_record(MEMBERSHIP).history == history()
    assert archive.put_membership_history_record(history(), METADATA) == MEMBERSHIP
    assert len(list(tmp_path.glob(".staging-*"))) == (1 if failure == "cleanup" else 0)


def test_dependency_io_error_keeps_type(tmp_path: Path, monkeypatch: Any) -> None:
    archive = prepare(tmp_path)
    assert archive.put_membership_history_record(history(), METADATA) == MEMBERSHIP

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise ArchiveIOError("injected metadata dependency failure")

    monkeypatch.setattr(archive, "get_observation_record", fail)
    with pytest.raises(ArchiveIOError, match="metadata dependency"):
        archive.get_membership_history_record(MEMBERSHIP)
    with pytest.raises(ArchiveIOError, match="metadata dependency"):
        archive.put_membership_history_record(history(), METADATA)
