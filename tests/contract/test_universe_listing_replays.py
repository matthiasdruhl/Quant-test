"""Independent persisted query/report bytes and fail-closed historical joins."""

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

from quant_test.data import raw_archive
from quant_test.data.admission import AcceptedAvailability
from quant_test.data.listings import ListingHistory, ListingInterval
from quant_test.data.raw_archive import (
    ArchiveIOError,
    ListingHistoryRecordCorruptError,
    ListingHistoryRecordMissingError,
    LocalRawArchive,
    MembershipHistoryRecordCorruptError,
    MembershipHistoryRecordMissingError,
    ObservationRecordCorruptError,
    ObservationRecordMissingError,
    PayloadCorruptError,
    PayloadMissingError,
    ReceiptCorruptError,
    ReceiptMissingError,
    UniverseListingReplayCorruptError,
    UniverseListingReplayMissingError,
)
from quant_test.data.receipts import AdmissionReceipt, decode_receipt
from quant_test.data.universe_listing_replays import (
    UniverseListingReplay,
    UniverseListingReplayFormatError,
    UniverseListingReplayManifest,
    build_universe_listing_replay,
    decode_universe_listing_replay,
    encode_universe_listing_replay,
)
from quant_test.data.universes import (
    MembershipHistory,
    MembershipInterval,
    membership_observation_id,
)
from quant_test.data.versions import ObservationVersion

FIXTURES = Path(__file__).parents[1] / "fixtures"
ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
LISTING = "75458f1ed9c9881c187dd5bde8be1516bad05ace7a5ceb2f0f849f4fcfd7734e"
MEMBER = "40967a79c8ff080be9cea2f339f56c4aa45630c0c42a1eb8684dd355e5c01c79"
LIST_META = "e12a322781e5344136f36db81e55ce679b03e754b35db4a33442d81d39af3ac7"
MEM_META = "a4560cb475bd9e07960e48772bcf1ce99e4a6fd98fee585932613c0e63936002"
LIST_RECEIPT = "620e2e9d81ece91590e1a66d1a8e9e933edba76eb1b422a68f0441f848396011"
MEM_RECEIPT = "6fa893e84548402199a71a31c1852b6cc8291899ecd304100cf02f2bf80dfea1"
UNIVERSE = " research:large-cap "
E = datetime(2021, 6, 1, tzinfo=UTC)
D = datetime(2025, 1, 3, 11, tzinfo=UTC)
# Literal hash below is independently computed from the hand-written JSON fixture.
REPLAY = "36acbceb24abb1b9956e25fe59e066963d0b33559190fae4a9f76fd561d0be27"


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def publish_bytes(archive: LocalRawArchive, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    archive.put(digest, payload)
    return digest


def fixture_bytes() -> bytes:
    return (FIXTURES / "universe-listing-replay-v1.json").read_bytes()


def manifest(**kwargs: Any) -> UniverseListingReplayManifest:
    fields = dict(
        listing_history_record_sha256s=[LISTING],
        membership_history_record_sha256s=[MEMBER],
        universe_id=UNIVERSE,
        membership_source_id="membership-reference",
        listing_source_id="listing-reference",
        venue="XNYS",
        effective_at=E,
        decision_at=D,
    )
    fields.update(kwargs)
    return UniverseListingReplayManifest(**fields)


def prepare(tmp_path: Path) -> LocalRawArchive:
    archive = LocalRawArchive(tmp_path)
    archive.put(ABC, b"abc")
    # Load independent literal chains; no replay encoder creates dependencies.
    for kind in ("listing", "membership"):
        for suffix in ("receipt", "observation-record", "history-record"):
            publish_bytes(archive, (FIXTURES / f"{kind}-{suffix}-v1.json").read_bytes())
    return archive


def raw_receipt(kind: str) -> AdmissionReceipt:
    return decode_receipt((FIXTURES / f"{kind}-receipt-v1.json").read_bytes())


def change_receipt(
    kind: str,
    *,
    security: str = "security-1",
    source: str | None = None,
    universe: str = UNIVERSE,
    version_id: str | None = None,
    day: int = 3,
    hour: int | None = None,
) -> AdmissionReceipt:
    receipt = raw_receipt(kind)
    raw = receipt.raw
    key = replace(
        raw.key,
        security_id=security,
        source_id=raw.key.source_id if source is None else source,
        observation_id=(
            membership_observation_id(universe) if kind == "membership" else raw.key.observation_id
        ),
    )
    return replace(
        receipt,
        raw=replace(
            raw,
            key=key,
            version_id=raw.version_id if version_id is None else version_id,
            published_at=replace(
                raw.published_at, parsed_value=datetime(2025, 1, day, 10, tzinfo=UTC)
            ),
            source_available_at=replace(
                raw.source_available_at,
                parsed_value=datetime(
                    2025,
                    1,
                    day,
                    11 if kind == "listing" else 10,
                    0 if kind == "listing" else 30,
                    tzinfo=UTC,
                )
                if hour is None
                else datetime(2025, 1, day, hour, tzinfo=UTC),
            ),
        ),
    )


def version(receipt: AdmissionReceipt, rank: int = 0) -> ObservationVersion:
    assert isinstance(receipt.result, AcceptedAvailability)
    return ObservationVersion(
        receipt.raw.key,
        receipt.raw.version_id,
        rank,
        receipt.result.availability,
        receipt.source_uri,
        receipt.license_id,
        receipt.content_sha256,
        False,
    )


def publish_member(
    archive: LocalRawArchive,
    raw: AdmissionReceipt,
    intervals: tuple[MembershipInterval, ...],
    rank: int = 0,
    universe: str = UNIVERSE,
) -> str:
    receipt_digest = archive.put_receipt(raw, b"abc")
    supplied = version(raw, rank)
    metadata = archive.put_observation_record(supplied, receipt_digest)
    return archive.put_membership_history_record(
        MembershipHistory(universe, supplied, intervals), metadata
    )


def publish_listing(
    archive: LocalRawArchive,
    raw: AdmissionReceipt,
    intervals: tuple[ListingInterval, ...],
    rank: int = 0,
) -> str:
    receipt_digest = archive.put_receipt(raw, b"abc")
    supplied = version(raw, rank)
    metadata = archive.put_observation_record(supplied, receipt_digest)
    return archive.put_listing_history_record(ListingHistory(supplied, intervals), metadata)


def interval(symbol: str = "NEW") -> ListingInterval:
    return ListingInterval("issuer-2", symbol, "XNYS", "USD", datetime(2022, 1, 1, tzinfo=UTC))


def reopen(archive: LocalRawArchive, query: UniverseListingReplayManifest) -> UniverseListingReplay:
    digest = archive.put_universe_listing_replay(query)
    return archive.get_universe_listing_replay(digest)


def test_literal_bytes_hash_report_and_fresh_archive_reopen(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    expected = fixture_bytes()
    assert hashlib.sha256(expected).hexdigest() == REPLAY
    replay = build_universe_listing_replay(archive, manifest())
    assert encode_universe_listing_replay(replay) == expected
    assert replay.universe_listing_replay_sha256 == REPLAY
    assert replay.result.membership.member_ids == ("security-1",)
    assert replay.result.matches[0].interval.symbol == "NEW"
    assert replay.result.unresolved_member_ids == ()
    assert replay.listing_records[0].observation_record.receipt_sha256 == LIST_RECEIPT
    assert replay.membership_records[0].observation_record.receipt_sha256 == MEM_RECEIPT
    assert json.loads(expected)["report"] == {
        "membership_selections": [
            {"membership_history_record_sha256": MEMBER, "matched_interval_index": 0}
        ],
        "listing_lookups": [
            {
                "security_id": "security-1",
                "listing_history_record_sha256": LISTING,
                "matched_interval_index": 1,
            }
        ],
    }
    before = {p.name for p in tmp_path.iterdir()}
    assert archive.put_universe_listing_replay(manifest()) == REPLAY
    assert {p.name for p in tmp_path.iterdir()} == before | {REPLAY}
    assert archive.put_universe_listing_replay(manifest()) == REPLAY
    fresh = LocalRawArchive(tmp_path)
    assert fresh.get_universe_listing_replay(REPLAY) == replay
    assert decode_universe_listing_replay(expected, fresh) == replay
    with pytest.raises(FrozenInstanceError):
        replay.result = replay.result  # type: ignore[misc]
    with pytest.raises(TypeError):
        UniverseListingReplay(
            replay.manifest, replay.listing_records, replay.membership_records, replay.result
        )  # type: ignore[call-arg]


def test_independent_release_cutoffs_and_missing_vs_negative_mapping(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    query = manifest(effective_at=datetime(2023, 7, 1, tzinfo=UTC))
    before = reopen(
        archive, replace(query, decision_at=datetime(2025, 1, 3, 10, 29, 59, 999999, tzinfo=UTC))
    )
    assert (
        before.result.membership.member_ids == ()
        and before.result.membership.selected_versions == ()
    )
    assert json.loads(encode_universe_listing_replay(before))["report"] == {
        "membership_selections": [],
        "listing_lookups": [],
    }
    member_cutoff = reopen(
        archive, replace(query, decision_at=datetime(2025, 1, 3, 10, 30, tzinfo=UTC))
    )
    assert member_cutoff.result.membership.member_ids == ("security-1",)
    assert member_cutoff.result.unresolved_member_ids == ("security-1",)
    assert json.loads(encode_universe_listing_replay(member_cutoff))["report"][
        "listing_lookups"
    ] == [
        {
            "security_id": "security-1",
            "listing_history_record_sha256": None,
            "matched_interval_index": None,
        }
    ]
    listed_cutoff = reopen(archive, query)
    assert listed_cutoff.result.unresolved_member_ids == ("security-1",)
    assert json.loads(encode_universe_listing_replay(listed_cutoff))["report"][
        "listing_lookups"
    ] == [
        {
            "security_id": "security-1",
            "listing_history_record_sha256": LISTING,
            "matched_interval_index": None,
        }
    ]
    exit_query = reopen(archive, manifest(effective_at=datetime(2022, 1, 1, tzinfo=UTC)))
    assert exit_query.result.membership.member_ids == ()
    assert json.loads(encode_universe_listing_replay(exit_query))["report"] == {
        "membership_selections": [
            {"membership_history_record_sha256": MEMBER, "matched_interval_index": None}
        ],
        "listing_lookups": [],
    }
    entry = reopen(archive, manifest(effective_at=datetime(2020, 1, 1, tzinfo=UTC)))
    assert entry.result.membership.member_ids == ("security-1",)
    assert entry.result.matches[0].interval.symbol == "OLD"


def test_late_independent_corrections_empty_replacements_and_stable_security_joins(
    tmp_path: Path,
) -> None:
    archive = prepare(tmp_path)
    original = archive.get_membership_history_record(MEMBER).history
    other = publish_member(
        archive, change_receipt("membership", security="security-2"), original.intervals
    )
    reused = publish_listing(
        archive, change_receipt("listing", security="security-2"), (interval(),)
    )
    corrected_listing = publish_listing(
        archive,
        change_receipt("listing", version_id="listing-v2", day=4, hour=12),
        (interval("RETURN"),),
        rank=1,
    )
    removed = publish_member(
        archive,
        change_receipt("membership", version_id="membership-v2", day=4, hour=13),
        (
            original.intervals[0],
            MembershipInterval(datetime(2023, 1, 1, tzinfo=UTC), datetime(2023, 6, 1, tzinfo=UTC)),
        ),
        rank=1,
    )
    empty = publish_member(
        archive,
        change_receipt("membership", version_id="membership-v3", day=5),
        (),
        rank=2,
    )
    query = manifest(
        listing_history_record_sha256s=[corrected_listing, reused, LISTING],
        membership_history_record_sha256s=[empty, removed, other, MEMBER],
        effective_at=datetime(2023, 7, 1, tzinfo=UTC),
        decision_at=datetime(2025, 1, 4, 11, 59, 59, 999999, tzinfo=UTC),
    )
    earlier = reopen(archive, query)
    assert earlier.result.membership.member_ids == ("security-1", "security-2")
    assert earlier.result.unresolved_member_ids == ("security-1",)
    assert tuple(match.version.key.security_id for match in earlier.result.matches) == (
        "security-2",
    )
    at_listing = reopen(archive, replace(query, decision_at=datetime(2025, 1, 4, 12, tzinfo=UTC)))
    assert [(m.version.key.security_id, m.interval.symbol) for m in at_listing.result.matches] == [
        ("security-1", "RETURN"),
        ("security-2", "NEW"),
    ]
    at_member = reopen(archive, replace(query, decision_at=datetime(2025, 1, 4, 13, tzinfo=UTC)))
    assert at_member.result.membership.member_ids == ("security-2",)
    assert json.loads(encode_universe_listing_replay(at_member))["report"][
        "membership_selections"
    ] == [
        {"membership_history_record_sha256": removed, "matched_interval_index": None},
        {"membership_history_record_sha256": other, "matched_interval_index": 1},
    ]
    at_empty = reopen(
        archive,
        replace(query, effective_at=E, decision_at=datetime(2025, 1, 5, 10, 30, tzinfo=UTC)),
    )
    assert at_empty.result.membership.member_ids == ("security-2",)
    assert json.loads(encode_universe_listing_replay(at_empty))["report"]["membership_selections"][
        0
    ] == {
        "membership_history_record_sha256": empty,
        "matched_interval_index": None,
    }
    # Current ticker reuse never binds the delisted original member to security-2.
    assert earlier.result.listing_results[0].security_id == "security-1"
    assert earlier.result.listing_results[0].selected_versions[0].key.security_id == "security-1"


def test_original_unsorted_tuple_indices_and_equal_symbols_use_full_version_identity(
    tmp_path: Path,
) -> None:
    archive = prepare(tmp_path)
    member = archive.get_membership_history_record(MEMBER)
    listing = archive.get_listing_history_record(LISTING)
    reordered_member = archive.put_membership_history_record(
        replace(member.history, intervals=tuple(reversed(member.history.intervals))),
        MEM_META,
    )
    reordered_listing = archive.put_listing_history_record(
        replace(listing.history, intervals=tuple(reversed(listing.history.intervals))),
        LIST_META,
    )
    other = publish_member(
        archive, change_receipt("membership", security="security-2"), member.history.intervals
    )
    same_symbol = publish_listing(
        archive,
        change_receipt("listing", security="security-2"),
        (ListingInterval("issuer-2", "NEW", "XNYS", "USD", datetime(2020, 1, 1, tzinfo=UTC)),),
    )
    query = manifest(
        listing_history_record_sha256s=[same_symbol, reordered_listing],
        membership_history_record_sha256s=[other, reordered_member],
    )
    replay = reopen(archive, query)
    assert [(m.version.key.security_id, m.interval.symbol) for m in replay.result.matches] == [
        ("security-1", "NEW"),
        ("security-2", "NEW"),
    ]
    report = json.loads(encode_universe_listing_replay(replay))["report"]
    assert report["membership_selections"] == [
        {"membership_history_record_sha256": reordered_member, "matched_interval_index": 1},
        {"membership_history_record_sha256": other, "matched_interval_index": 0},
    ]
    assert report["listing_lookups"] == [
        {
            "security_id": "security-1",
            "listing_history_record_sha256": reordered_listing,
            "matched_interval_index": 0,
        },
        {
            "security_id": "security-2",
            "listing_history_record_sha256": same_symbol,
            "matched_interval_index": 0,
        },
    ]


def test_exact_scope_filters_isolate_full_universe_sources_and_venue(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    base = archive.get_membership_history_record(MEMBER).history
    extra_universe = UNIVERSE + ":tail"
    extra = publish_member(
        archive,
        change_receipt("membership", universe=extra_universe),
        base.intervals,
        universe=extra_universe,
    )
    other_source = publish_member(
        archive, change_receipt("membership", source="other-source"), base.intervals
    )
    query = manifest(membership_history_record_sha256s=[MEMBER, extra, other_source])
    assert reopen(archive, query).result.membership.member_ids == ("security-1",)
    for filters in (
        {"universe_id": UNIVERSE.strip()},
        {"membership_source_id": " membership-reference"},
    ):
        assert reopen(archive, replace(query, **filters)).result.membership.selected_versions == ()
    for filters in ({"listing_source_id": "listing-reference "}, {"venue": " XNYS"}):
        result = reopen(archive, replace(query, **filters)).result
        assert result.membership.member_ids == ("security-1",)
        assert result.unresolved_member_ids == ("security-1",)
    assert (
        reopen(archive, replace(query, universe_id=extra_universe))
        .result.membership.selected_versions[0]
        .key.observation_id.endswith(extra_universe)
    )
    assert (
        reopen(archive, replace(query, membership_source_id="other-source"))
        .result.membership.selected_versions[0]
        .key.source_id
        == "other-source"
    )


def test_manifest_snapshots_sorted_membership_permutation_and_empty_behavior(
    tmp_path: Path,
) -> None:
    archive = prepare(tmp_path)
    member = archive.get_membership_history_record(MEMBER)
    other = publish_member(
        archive, change_receipt("membership", security="security-2"), member.history.intervals
    )
    inputs = [other, MEMBER]
    query = manifest(membership_history_record_sha256s=inputs)
    inputs.clear()
    assert query.membership_history_record_sha256s == tuple(sorted((MEMBER, other)))
    assert encode_universe_listing_replay(
        build_universe_listing_replay(archive, query)
    ) == encode_universe_listing_replay(
        build_universe_listing_replay(
            archive, manifest(membership_history_record_sha256s=[MEMBER, other])
        )
    )
    with pytest.raises(FrozenInstanceError):
        query.venue = "OTHER"  # type: ignore[misc]
    empty = manifest(listing_history_record_sha256s=(), membership_history_record_sha256s=[])
    artifact = reopen(archive, empty)
    assert artifact.result.membership.selected_versions == ()
    assert artifact.result.membership.member_ids == artifact.result.unresolved_member_ids == ()
    assert artifact.result.listing_results == artifact.result.matches == ()
    with pytest.raises(ValueError, match="archive"):
        build_universe_listing_replay(None, empty)  # type: ignore[arg-type]
    # Standalone empty build checks argument type, not filesystem liveness.
    root = tmp_path / "empty"
    root.mkdir()
    transient = LocalRawArchive(root)
    root.rmdir()
    assert build_universe_listing_replay(transient, empty).result.matches == ()
    with pytest.raises(ArchiveIOError):
        transient.put_universe_listing_replay(empty)


@pytest.mark.parametrize(
    "field", ["listing_history_record_sha256s", "membership_history_record_sha256s"]
)
@pytest.mark.parametrize(
    "invalid", [None, "", {}, set(), iter(()), [None], ["a" * 63], ["A" * 64], [LISTING, LISTING]]
)
def test_invalid_collections_and_duplicate_digests_reject_before_reads(
    field: str, invalid: Any
) -> None:
    with pytest.raises(ValueError):
        manifest(**{field: invalid})


def test_list_tuple_subclasses_are_not_explicit_collection_inputs() -> None:
    class Items(list[str]):
        pass

    with pytest.raises(ValueError):
        manifest(listing_history_record_sha256s=Items())


@pytest.mark.parametrize(
    "field", ["universe_id", "membership_source_id", "listing_source_id", "venue"]
)
@pytest.mark.parametrize("invalid", [None, "", " \t", 1])
def test_invalid_exact_filters_fail(field: str, invalid: Any) -> None:
    with pytest.raises(ValueError):
        manifest(**{field: invalid})


class CustomZone(tzinfo):
    def utcoffset(self, value: datetime | None) -> timedelta:
        return timedelta(0)


class DateTimeSubclass(datetime):
    pass


@pytest.mark.parametrize("field", ["effective_at", "decision_at"])
@pytest.mark.parametrize(
    "invalid",
    [
        None,
        date(2021, 1, 1),
        datetime(2021, 1, 1),
        DateTimeSubclass(2021, 1, 1, tzinfo=UTC),
        datetime(2021, 1, 1, tzinfo=CustomZone()),
        datetime.min.replace(tzinfo=timezone(timedelta(hours=23))),
        datetime.max.replace(tzinfo=timezone(-timedelta(hours=23))),
        datetime(2021, 3, 14, 2, 30, tzinfo=ZoneInfo("America/New_York"), fold=0),
        datetime(2021, 3, 14, 2, 30, tzinfo=ZoneInfo("America/New_York"), fold=1),
    ],
)
def test_invalid_scalar_times_fail_without_coercion(field: str, invalid: Any) -> None:
    with pytest.raises(ValueError):
        manifest(**{field: invalid})


def test_scalar_equivalent_offsets_folds_and_effective_decision_order(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    plus = timezone(timedelta(hours=5, minutes=30), "reference")
    equivalent = manifest(effective_at=E.astimezone(plus), decision_at=D.astimezone(plus))
    assert equivalent == manifest()
    assert (
        encode_universe_listing_replay(build_universe_listing_replay(archive, equivalent))
        == fixture_bytes()
    )
    zone = ZoneInfo("America/New_York")
    first = datetime(2021, 11, 7, 1, 30, tzinfo=zone, fold=0)
    second = first.replace(fold=1)
    query = manifest(effective_at=first, decision_at=second)
    assert query.effective_at == datetime(2021, 11, 7, 5, 30, tzinfo=UTC)
    assert query.decision_at == datetime(2021, 11, 7, 6, 30, tzinfo=UTC)
    assert query.effective_at.fold == query.decision_at.fold == 0
    with pytest.raises(ValueError, match="must not follow"):
        manifest(effective_at=second, decision_at=first)
    assert manifest(effective_at=first, decision_at=first).effective_at == query.effective_at
    assert first.fold == 0 and second.fold == 1
    assert manifest(effective_at=E.replace(fold=1)).effective_at.fold == 0


@pytest.mark.parametrize(
    "file_name,key",
    [
        ("UTC", "NoSuch/ReplayZone"),
        ("UTC", "America/New_York"),
        ("GMT", "UTC"),
    ],
)
def test_zoneinfo_key_must_reproduce_offset_and_name(file_name: str, key: str) -> None:
    # Independent zero-transition TZif v1 with one zero-offset named type.
    abbreviation = file_name.encode("ascii") + b"\0"
    tzif = (
        b"TZif\0"
        + b"\0" * 15
        + struct.pack(">6l", 0, 0, 0, 0, 1, len(abbreviation))
        + struct.pack(">lbb", 0, 0, 0)
        + abbreviation
    )
    zone = ZoneInfo.from_file(BytesIO(tzif), key=key)
    assert E.replace(tzinfo=zone).utcoffset() == timedelta(0)
    with pytest.raises(ValueError, match="key"):
        manifest(effective_at=E.replace(tzinfo=zone))


@pytest.mark.parametrize("kind", ["listing", "membership"])
@pytest.mark.parametrize("contradiction", ["same_version", "same_rank", "availability"])
def test_global_catalog_validation_includes_irrelevant_future_histories(
    tmp_path: Path,
    kind: str,
    contradiction: str,
) -> None:
    archive = prepare(tmp_path)
    security = "unmentioned-security"
    source = "irrelevant-source"
    first_raw = change_receipt(kind, security=security, source=source, day=20, version_id="v1")
    if kind == "membership":
        first = publish_member(archive, first_raw, (), rank=0)
    else:
        first = publish_listing(archive, first_raw, (), rank=0)
    second_raw = change_receipt(
        kind,
        security=security,
        source=source,
        day=19 if contradiction == "availability" else 21,
        version_id="v1" if contradiction == "same_version" else "v2",
    )
    rank = 0 if contradiction == "same_rank" else 1
    if kind == "membership":
        second = publish_member(archive, second_raw, (), rank=rank)
        query = manifest(membership_history_record_sha256s=[MEMBER, first, second])
    else:
        second = publish_listing(archive, second_raw, (), rank=rank)
        query = manifest(listing_history_record_sha256s=[LISTING, first, second])
    before = {p.name for p in tmp_path.iterdir()}
    with pytest.raises(ValueError, match="duplicate|contradicts"):
        archive.put_universe_listing_replay(query)
    assert {p.name for p in tmp_path.iterdir()} == before
    # Rehashed outer bytes cannot hide catalog contradictions on reopen either.
    document = json.loads(fixture_bytes())
    document["manifest"]["listing_history_record_sha256s"] = query.listing_history_record_sha256s
    document["manifest"]["membership_history_record_sha256s"] = (
        query.membership_history_record_sha256s
    )
    with pytest.raises(UniverseListingReplayCorruptError):
        archive.get_universe_listing_replay(publish_bytes(archive, canonical(document)))


@pytest.mark.parametrize("kind", ["listing", "membership"])
def test_conflicting_assertions_pinning_same_version_are_not_merged(
    tmp_path: Path, kind: str
) -> None:
    archive = prepare(tmp_path)
    if kind == "listing":
        original = archive.get_listing_history_record(LISTING)
        conflicting = archive.put_listing_history_record(
            replace(original.history, intervals=()), LIST_META
        )
        query = manifest(listing_history_record_sha256s=[LISTING, conflicting])
    else:
        original_member = archive.get_membership_history_record(MEMBER)
        conflicting = archive.put_membership_history_record(
            replace(original_member.history, intervals=()), MEM_META
        )
        query = manifest(membership_history_record_sha256s=[MEMBER, conflicting])
    with pytest.raises(ValueError, match="duplicate version_id"):
        build_universe_listing_replay(archive, query)


def test_direct_model_type_correspondence_and_encoder_contract(tmp_path: Path) -> None:
    archive = prepare(tmp_path)
    replay = build_universe_listing_replay(archive, manifest())
    for args in (
        (None, (), ()),
        (manifest(), [], replay.membership_records),
        (manifest(), replay.listing_records, []),
        (manifest(), (replay.membership_records[0],), replay.membership_records),
        (manifest(), replay.listing_records, (replay.listing_records[0],)),
        (manifest(), (), replay.membership_records),
        (manifest(), replay.listing_records, ()),
    ):
        with pytest.raises(ValueError):
            UniverseListingReplay(*args)  # type: ignore[arg-type]
    for invalid in (None, manifest(), {}):
        with pytest.raises(ValueError):
            encode_universe_listing_replay(invalid)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        build_universe_listing_replay(archive, None)  # type: ignore[arg-type]
    for invalid in (None, "", "A" * 64):
        with pytest.raises(ValueError):
            archive.get_universe_listing_replay(invalid)  # type: ignore[arg-type]
    with pytest.raises(UniverseListingReplayCorruptError):
        archive.get_universe_listing_replay(LISTING)
    # Bare construction/encoding does not assert that dependencies still exist.
    for p in tmp_path.iterdir():
        p.unlink()
    assert (
        encode_universe_listing_replay(
            UniverseListingReplay(manifest(), replay.listing_records, replay.membership_records)
        )
        == fixture_bytes()
    )
    with pytest.raises(ListingHistoryRecordMissingError):
        build_universe_listing_replay(archive, manifest())


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(schema_version=2),
        lambda d: d.update(schema_version=True),
        lambda d: d.update(schema_version=1.0),
        lambda d: d.update(replay_policy_id="unknown"),
        lambda d: d.update(extra=None),
        lambda d: d.pop("report"),
        lambda d: d["manifest"].update(extra=None),
        lambda d: d["manifest"].pop("venue"),
        lambda d: d["manifest"].update(effective_at="2021-06-01T00:00:00Z"),
        lambda d: d["manifest"].update(effective_at="2021-06-01T00:00:00.000000+00:00"),
        lambda d: d["manifest"].update(effective_at=None),
        lambda d: d["manifest"].update(decision_at="2025-01-03T11:00:00.0Z"),
        lambda d: d["manifest"].update(decision_at="2025-01-03T11:00:00"),
        lambda d: d["manifest"].update(decision_at="2020-01-03T11:00:00.000000Z"),
        lambda d: d["manifest"].update(listing_history_record_sha256s={}),
        lambda d: d["manifest"].update(membership_history_record_sha256s=[MEMBER, MEMBER]),
        lambda d: d["manifest"].update(universe_id=" "),
        lambda d: d["report"].update(extra=[]),
        lambda d: d["report"].pop("listing_lookups"),
        lambda d: d["report"].update(membership_selections={}),
        lambda d: d["report"].update(listing_lookups=None),
        lambda d: d["report"]["membership_selections"].append(True),
        lambda d: d["report"]["membership_selections"][0].update(extra=None),
        lambda d: d["report"]["membership_selections"][0].pop("matched_interval_index"),
        lambda d: d["report"]["membership_selections"][0].update(
            membership_history_record_sha256=None
        ),
        lambda d: d["report"]["membership_selections"][0].update(
            membership_history_record_sha256="a" * 64
        ),
        lambda d: d["report"]["membership_selections"].append(
            d["report"]["membership_selections"][0].copy()
        ),
        lambda d: d["report"]["membership_selections"][0].update(matched_interval_index=True),
        lambda d: d["report"]["membership_selections"][0].update(matched_interval_index=0.0),
        lambda d: d["report"]["membership_selections"][0].update(matched_interval_index=-1),
        lambda d: d["report"]["listing_lookups"][0].update(extra=None),
        lambda d: d["report"]["listing_lookups"][0].pop("security_id"),
        lambda d: d["report"]["listing_lookups"][0].update(security_id=" "),
        lambda d: d["report"]["listing_lookups"][0].update(listing_history_record_sha256="a" * 64),
        lambda d: d["report"]["listing_lookups"][0].update(listing_history_record_sha256=None),
        lambda d: d["report"]["listing_lookups"][0].update(matched_interval_index=False),
        lambda d: d["report"]["listing_lookups"][0].update(matched_interval_index=1.0),
        lambda d: d["report"]["listing_lookups"][0].update(matched_interval_index=-1),
        lambda d: d["report"]["listing_lookups"][0].update(matched_interval_index="1"),
        lambda d: d["report"].update(listing_lookups=[]),
    ],
)
def test_malformed_and_statically_impossible_report_rejects_before_reads(
    tmp_path: Path,
    monkeypatch: Any,
    mutation: Any,
) -> None:
    archive = LocalRawArchive(tmp_path)
    document = json.loads(fixture_bytes())
    mutation(document)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("invalid replay read a dependency")

    monkeypatch.setattr(archive, "get_listing_history_record", forbidden)
    monkeypatch.setattr(archive, "get_membership_history_record", forbidden)
    with pytest.raises(UniverseListingReplayFormatError):
        decode_universe_listing_replay(canonical(document), archive)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda b: b + b"\n",
        lambda b: b" " + b,
        lambda b: json.dumps(json.loads(b), indent=2).encode("ascii"),
        lambda b: b.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1'),
        lambda b: b.replace(
            b'"matched_interval_index":1', b'"matched_interval_index":1,"matched_interval_index":1'
        ),
        lambda b: b.replace(b'"schema_version":1', b'"schema_version":NaN'),
        lambda b: b.replace(b'"schema_version":1', b'"schema_version":Infinity'),
        lambda b: b"[]",
        lambda b: b"\xff",
    ],
)
def test_noncanonical_and_duplicate_json_reject_before_reads(
    tmp_path: Path, monkeypatch: Any, mutation: Any
) -> None:
    archive = LocalRawArchive(tmp_path)

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("noncanonical replay read a dependency")

    monkeypatch.setattr(archive, "get_listing_history_record", forbidden)
    monkeypatch.setattr(archive, "get_membership_history_record", forbidden)
    with pytest.raises(UniverseListingReplayFormatError):
        decode_universe_listing_replay(mutation(fixture_bytes()), archive)


@pytest.mark.parametrize("invalid", [None, "", bytearray(b"{}"), memoryview(b"{}")])
def test_decoder_requires_immutable_bytes(invalid: Any) -> None:
    with pytest.raises(UniverseListingReplayFormatError):
        decode_universe_listing_replay(invalid, None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["report"]["membership_selections"][0].update(matched_interval_index=1),
        lambda d: d["report"]["membership_selections"][0].update(matched_interval_index=100),
        lambda d: d["report"]["listing_lookups"][0].update(matched_interval_index=0),
        lambda d: d["report"]["listing_lookups"][0].update(matched_interval_index=100),
        lambda d: d["report"]["listing_lookups"][0].update(matched_interval_index=None),
        lambda d: d["report"]["listing_lookups"][0].update(
            listing_history_record_sha256=None, matched_interval_index=None
        ),
        lambda d: d["report"]["listing_lookups"][0].update(security_id="other-security"),
        lambda d: d["manifest"].update(effective_at="2022-01-01T00:00:00.000000Z"),
        lambda d: d["manifest"].update(decision_at="2025-01-03T10:30:00.000000Z"),
    ],
)
def test_rehashed_semantic_report_or_query_drift_is_corrupt(tmp_path: Path, mutation: Any) -> None:
    archive = prepare(tmp_path)
    document = json.loads(fixture_bytes())
    mutation(document)
    payload = canonical(document)
    with pytest.raises(UniverseListingReplayFormatError, match="recomputed"):
        decode_universe_listing_replay(payload, archive)
    with pytest.raises(UniverseListingReplayCorruptError):
        archive.get_universe_listing_replay(publish_bytes(archive, payload))


def test_static_multimember_order_duplicates_and_counts_reject_before_reads(
    tmp_path: Path, monkeypatch: Any
) -> None:
    archive = prepare(tmp_path)
    original = archive.get_membership_history_record(MEMBER)
    other = publish_member(
        archive, change_receipt("membership", security="security-2"), original.history.intervals
    )
    listing = publish_listing(
        archive, change_receipt("listing", security="security-2"), (interval(),)
    )
    query = manifest(
        membership_history_record_sha256s=[MEMBER, other],
        listing_history_record_sha256s=[LISTING, listing],
    )
    document = json.loads(
        encode_universe_listing_replay(build_universe_listing_replay(archive, query))
    )

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("statically impossible multi-member report read dependencies")

    with monkeypatch.context() as patch:
        patch.setattr(archive, "get_listing_history_record", forbidden)
        patch.setattr(archive, "get_membership_history_record", forbidden)
        mutations = [
            lambda d: d["report"]["listing_lookups"].reverse(),
            lambda d: d["report"]["listing_lookups"][1].update(security_id="security-1"),
            lambda d: d["report"]["listing_lookups"][1].update(
                listing_history_record_sha256=LISTING
            ),
            lambda d: d["manifest"]["membership_history_record_sha256s"].reverse(),
            lambda d: d["manifest"]["listing_history_record_sha256s"].reverse(),
        ]
        for mutation in mutations:
            changed = json.loads(canonical(document))
            mutation(changed)
            with pytest.raises(UniverseListingReplayFormatError):
                decode_universe_listing_replay(canonical(changed), archive)
    # Membership-row security order cannot be checked until dependencies reopen.
    document["report"]["membership_selections"].reverse()
    with pytest.raises(UniverseListingReplayFormatError, match="recomputed"):
        decode_universe_listing_replay(canonical(document), archive)


def test_valid_changed_query_or_dependency_and_correct_report_is_new_assertion(
    tmp_path: Path,
) -> None:
    archive = prepare(tmp_path)
    original = reopen(archive, manifest())
    changed = json.loads(fixture_bytes())
    changed["manifest"]["universe_id"] = "research:large-cap"
    changed["report"] = {"membership_selections": [], "listing_lookups": []}
    new_query = decode_universe_listing_replay(canonical(changed), archive)
    assert new_query.result.membership.member_ids == ()
    assert new_query.universe_listing_replay_sha256 != REPLAY
    record = archive.get_listing_history_record(LISTING)
    altered = archive.put_listing_history_record(
        replace(
            record.history, intervals=(replace(record.history.intervals[1], symbol="ASSERTED"),)
        ),
        LIST_META,
    )
    changed = json.loads(fixture_bytes())
    changed["manifest"]["listing_history_record_sha256s"] = [altered]
    changed["report"]["listing_lookups"][0].update(
        listing_history_record_sha256=altered, matched_interval_index=0
    )
    new_assertion = archive.get_universe_listing_replay(publish_bytes(archive, canonical(changed)))
    assert new_assertion.result.matches[0].interval.symbol == "ASSERTED"
    assert original.result.matches[0].interval.symbol == "NEW"


GRAPH = [
    (REPLAY, "replay", UniverseListingReplayMissingError, UniverseListingReplayCorruptError),
    (LISTING, "listing", ListingHistoryRecordMissingError, ListingHistoryRecordCorruptError),
    (
        MEMBER,
        "membership",
        MembershipHistoryRecordMissingError,
        MembershipHistoryRecordCorruptError,
    ),
    (LIST_META, "listing_metadata", ObservationRecordMissingError, ObservationRecordCorruptError),
    (MEM_META, "membership_metadata", ObservationRecordMissingError, ObservationRecordCorruptError),
    (LIST_RECEIPT, "listing_receipt", ReceiptMissingError, ReceiptCorruptError),
    (MEM_RECEIPT, "membership_receipt", ReceiptMissingError, ReceiptCorruptError),
    (ABC, "payload", PayloadMissingError, PayloadCorruptError),
]


@pytest.mark.parametrize("digest,name,missing,corrupt", GRAPH)
def test_missing_any_graph_node_fails_whole_replay_without_fallback(
    tmp_path: Path,
    digest: str,
    name: str,
    missing: type[Exception],
    corrupt: type[Exception],
) -> None:
    archive = prepare(tmp_path)
    assert archive.put_universe_listing_replay(manifest()) == REPLAY
    (tmp_path / digest).unlink()
    with pytest.raises(missing):
        archive.get_universe_listing_replay(REPLAY)
    if name != "replay":
        with pytest.raises(missing):
            archive.put_universe_listing_replay(manifest())


@pytest.mark.parametrize("digest,name,missing,corrupt", GRAPH)
def test_corrupt_any_graph_node_never_returns_partial_or_repairs(
    tmp_path: Path,
    digest: str,
    name: str,
    missing: type[Exception],
    corrupt: type[Exception],
) -> None:
    archive = prepare(tmp_path)
    assert archive.put_universe_listing_replay(manifest()) == REPLAY
    path = tmp_path / digest
    path.chmod(0o600)
    path.write_bytes(b"corrupt")
    with pytest.raises(corrupt):
        archive.get_universe_listing_replay(REPLAY)
    with pytest.raises(PayloadCorruptError if name == "replay" else corrupt):
        archive.put_universe_listing_replay(manifest())
    assert path.read_bytes() == b"corrupt"


@pytest.mark.parametrize("kind", ["listing", "membership"])
@pytest.mark.parametrize("node", ["history", "metadata", "receipt"])
def test_wrong_typed_dependency_keeps_requested_typed_error(
    tmp_path: Path, kind: str, node: str
) -> None:
    archive = prepare(tmp_path)
    history_digest = LISTING if kind == "listing" else MEMBER
    error: type[Exception]
    if node == "history":
        new_digest = MEMBER if kind == "listing" else LISTING
        error = (
            ListingHistoryRecordCorruptError
            if kind == "listing"
            else MembershipHistoryRecordCorruptError
        )
    else:
        doc = json.loads(archive.get(history_digest))
        if node == "metadata":
            doc["observation_record_sha256"] = LIST_RECEIPT if kind == "listing" else MEM_RECEIPT
            error = ObservationRecordCorruptError
        else:
            metadata = json.loads(archive.get(doc["observation_record_sha256"]))
            metadata["receipt_sha256"] = LIST_META if kind == "listing" else MEM_META
            doc["observation_record_sha256"] = publish_bytes(archive, canonical(metadata))
            error = ReceiptCorruptError
        new_digest = publish_bytes(archive, canonical(doc))
    field = f"{kind}_history_record_sha256s"
    query = manifest(**{field: [new_digest]})
    with pytest.raises(error):
        build_universe_listing_replay(archive, query)
    document = json.loads(fixture_bytes())
    document["manifest"][field] = [new_digest]
    report_field = "listing_lookups" if kind == "listing" else "membership_selections"
    document["report"][report_field][0][f"{kind}_history_record_sha256"] = new_digest
    with pytest.raises(error):
        archive.get_universe_listing_replay(publish_bytes(archive, canonical(document)))


@pytest.mark.parametrize("kind", ["listing", "membership"])
def test_irrelevant_future_dependency_failure_still_fails_replay(tmp_path: Path, kind: str) -> None:
    archive = prepare(tmp_path)
    raw = change_receipt(kind, security="unmentioned", source="irrelevant", day=20)
    if kind == "listing":
        other = publish_listing(archive, raw, ())
        query = manifest(listing_history_record_sha256s=[other, LISTING])
        error = ListingHistoryRecordMissingError
    else:
        other = publish_member(archive, raw, ())
        query = manifest(membership_history_record_sha256s=[other, MEMBER])
        error = MembershipHistoryRecordMissingError
    digest = archive.put_universe_listing_replay(query)
    (tmp_path / other).unlink()
    with pytest.raises(error):
        archive.get_universe_listing_replay(digest)


@pytest.mark.parametrize("kind", ["directory", "symlink", "fifo"])
def test_nonregular_outer_replay_rejects_without_blocking_or_following(
    tmp_path: Path, kind: str
) -> None:
    archive = prepare(tmp_path)
    path = tmp_path / REPLAY
    if kind == "directory":
        path.mkdir()
    elif kind == "symlink":
        path.symlink_to(tmp_path / LISTING)
    else:
        os.mkfifo(path)
    with pytest.raises(UniverseListingReplayCorruptError):
        archive.get_universe_listing_replay(REPLAY)
    assert archive.get_listing_history_record(LISTING).listing_history_record_sha256 == LISTING


def test_dependency_checks_precede_one_object_publication(tmp_path: Path, monkeypatch: Any) -> None:
    archive = prepare(tmp_path)
    (tmp_path / MEM_META).unlink()

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("replay published before dependencies verified")

    monkeypatch.setattr(archive, "put", forbidden)
    with pytest.raises(ObservationRecordMissingError):
        archive.put_universe_listing_replay(manifest())
    assert not (tmp_path / REPLAY).exists()


@pytest.mark.parametrize("failure", ["create", "write", "file_close", "verify", "link"])
def test_prepublication_fault_exposes_no_replay(
    tmp_path: Path, monkeypatch: Any, failure: str
) -> None:
    archive = prepare(tmp_path)
    real_open, real_close, real_read = os.open, os.close, LocalRawArchive._read
    expected_size = len(fixture_bytes())

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise OSError(errno.EIO, "injected replay publication failure")

    def fail_open(path: Any, flags: int, *args: Any, **kwargs: Any) -> int:
        return fail() if flags & os.O_CREAT else real_open(path, flags, *args, **kwargs)

    def fail_close(descriptor: int) -> None:
        metadata = os.fstat(descriptor)
        is_replay = stat.S_ISREG(metadata.st_mode) and metadata.st_size == expected_size
        real_close(descriptor)
        if is_replay:
            fail()

    def fail_verify(directory: int, name: str, digest: str) -> bytes:
        if name.startswith(".staging-") and digest == REPLAY:
            raise PayloadCorruptError("injected replay staged verification failure")
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
        archive.put_universe_listing_replay(manifest())
    assert not (tmp_path / REPLAY).exists()
    assert archive.get_membership_history_record(MEMBER).membership_history_record_sha256 == MEMBER


@pytest.mark.parametrize("failure", ["cleanup", "directory_close"])
def test_postpublication_fault_leaves_complete_object_retry_verifies(
    tmp_path: Path,
    monkeypatch: Any,
    failure: str,
) -> None:
    archive = prepare(tmp_path)
    real_close = os.close

    def fail_cleanup(*args: Any, **kwargs: Any) -> None:
        raise OSError(errno.EIO, "injected replay cleanup failure")

    def fail_close(descriptor: int) -> None:
        is_directory = (tmp_path / REPLAY).exists() and stat.S_ISDIR(os.fstat(descriptor).st_mode)
        real_close(descriptor)
        if is_directory:
            raise OSError(errno.EIO, "injected replay directory-close failure")

    with monkeypatch.context() as patch:
        patch.setattr(
            raw_archive.os,
            "unlink" if failure == "cleanup" else "close",
            fail_cleanup if failure == "cleanup" else fail_close,
        )
        with pytest.raises(ArchiveIOError):
            archive.put_universe_listing_replay(manifest())
    assert (tmp_path / REPLAY).read_bytes() == fixture_bytes()
    assert archive.get_universe_listing_replay(REPLAY).result.membership.member_ids == (
        "security-1",
    )
    assert archive.put_universe_listing_replay(manifest()) == REPLAY
    assert len(list(tmp_path.glob(".staging-*"))) == (1 if failure == "cleanup" else 0)


@pytest.mark.parametrize("api", ["get_listing_history_record", "get_membership_history_record"])
def test_dependency_io_failure_propagates_unchanged(
    tmp_path: Path, monkeypatch: Any, api: str
) -> None:
    archive = prepare(tmp_path)
    archive.put_universe_listing_replay(manifest())

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise ArchiveIOError("injected history dependency I/O")

    monkeypatch.setattr(archive, api, fail)
    with pytest.raises(ArchiveIOError, match="history dependency"):
        archive.get_universe_listing_replay(REPLAY)
    with pytest.raises(ArchiveIOError, match="history dependency"):
        archive.put_universe_listing_replay(manifest())


def test_listing_empty_replacement_only_its_key_and_equal_usability_rank_tie(
    tmp_path: Path,
) -> None:
    archive = prepare(tmp_path)
    member = archive.get_membership_history_record(MEMBER)
    other_member = publish_member(
        archive, change_receipt("membership", security="security-2"), member.history.intervals
    )
    other_listing = publish_listing(
        archive,
        change_receipt("listing", security="security-2"),
        (ListingInterval("issuer-2", "OTHER", "XNYS", "USD", datetime(2020, 1, 1, tzinfo=UTC)),),
    )
    empty = publish_listing(
        archive,
        change_receipt("listing", version_id="listing-v2", day=4, hour=12),
        (),
        rank=1,
    )
    query = manifest(
        listing_history_record_sha256s=[LISTING, empty, other_listing],
        membership_history_record_sha256s=[MEMBER, other_member],
        decision_at=datetime(2025, 1, 4, 11, 59, 59, 999999, tzinfo=UTC),
    )
    assert [
        (m.version.key.security_id, m.interval.symbol)
        for m in reopen(archive, query).result.matches
    ] == [
        ("security-1", "NEW"),
        ("security-2", "OTHER"),
    ]
    cutoff = replace(query, decision_at=datetime(2025, 1, 4, 12, tzinfo=UTC))
    negative = reopen(archive, cutoff)
    assert negative.result.membership.member_ids == ("security-1", "security-2")
    assert negative.result.unresolved_member_ids == ("security-1",)
    assert json.loads(encode_universe_listing_replay(negative))["report"]["listing_lookups"] == [
        {
            "security_id": "security-1",
            "listing_history_record_sha256": empty,
            "matched_interval_index": None,
        },
        {
            "security_id": "security-2",
            "listing_history_record_sha256": other_listing,
            "matched_interval_index": 0,
        },
    ]
    tied = publish_listing(
        archive,
        change_receipt("listing", version_id="listing-v3", day=4, hour=12),
        (ListingInterval("issuer-1", "RESTORED", "XNYS", "USD", datetime(2020, 1, 1, tzinfo=UTC)),),
        rank=2,
    )
    selected = reopen(
        archive,
        replace(cutoff, listing_history_record_sha256s=[LISTING, empty, tied, other_listing]),
    )
    assert selected.result.matches[0].version.revision_rank == 2
    assert selected.result.matches[0].interval.symbol == "RESTORED"
