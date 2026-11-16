"""Independent quantity/lifecycle references, assertion boundaries and failures."""

import hashlib
import struct
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal, localcontext
from io import BytesIO
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from quant_test.core.time import InformationAvailability
from quant_test.data.raw_archive import LocalRawArchive
from quant_test.strategies.targets import (
    TargetBatch,
    TargetBatchHistory,
    TargetBatchSelection,
    TargetBatchStatus,
    TargetDecisionContext,
    TargetProposal,
    TargetSnapshotAssertion,
    validate_target_batch_for_context,
)

D = datetime(2025, 1, 2, 14, tzinfo=UTC)
CUTOFF = datetime(2025, 1, 2, 13, tzinfo=UTC)
DATA = TargetSnapshotAssertion("data-1", CUTOFF, D)
PORTFOLIO = TargetSnapshotAssertion("portfolio-1", CUTOFF, D)


def proposal(security: str, weight: str) -> TargetProposal:
    return TargetProposal(security, "equity_weight", Decimal(weight))


def batch(**changes: Any) -> TargetBatch:
    fields = dict(
        run_id="run-1",
        strategy_id="S",
        strategy_version="version-1",
        batch_id="b1",
        decision_at=D,
        valid_until=D.replace(hour=18),
        data_cutoff_at=CUTOFF,
        data_snapshot=DATA,
        portfolio_snapshot=PORTFOLIO,
        targets=[proposal("A", ".10"), proposal("B", ".20")],
    )
    fields.update(changes)
    return TargetBatch(**fields)


def context(**changes: Any) -> TargetDecisionContext:
    fields = dict(
        run_id="run-1",
        strategy_id="S",
        strategy_version="version-1",
        decision_at=D,
        data_cutoff_at=CUTOFF,
        data_snapshot=DATA,
        portfolio_snapshot=PORTFOLIO,
    )
    fields.update(changes)
    return TargetDecisionContext(**fields)


def history(*records: TargetBatch, **changes: Any) -> TargetBatchHistory:
    fields = dict(
        run_id="run-1", strategy_id="S", strategy_version="version-1", batches=list(records)
    )
    fields.update(changes)
    return TargetBatchHistory(**fields)


def values(selection: TargetBatchSelection) -> tuple[tuple[str, Decimal], ...]:
    return tuple((target.security_id, target.equity_weight) for target in selection.active_targets)


def test_literal_complete_replacement_and_isolated_stream_reference() -> None:
    first = batch()
    second = batch(
        batch_id="b2",
        decision_at=D.replace(hour=15),
        valid_until=D.replace(hour=17),
        targets=[proposal("A", ".05")],
    )
    selected = history(second, first)
    # Expected literals come from ADR0004/0018, not from an allocator/implementation.
    assert values(selected.selected_at(D)) == (("A", Decimal(".10")), ("B", Decimal(".20")))
    assert values(selected.selected_at(D.replace(hour=15))) == (("A", Decimal(".05")),)
    assert selected.selected_at(D.replace(hour=15)).selected_batch is second
    other = batch(strategy_id="T", targets=[proposal("B", ".30")])
    other_history = history(other, strategy_id="T")
    assert values(other_history.selected_at(D.replace(hour=15))) == (("B", Decimal(".30")),)
    assert selected.batches == (first, second)
    assert other_history.batches == (other,)
    # No inherited B, synthetic zero, equity arithmetic, order or account effect.
    assert tuple(target.security_id for target in second.targets) == ("A",)


def test_literal_zero_active_empty_no_batch_and_expiry_are_distinct() -> None:
    first = batch(targets=[proposal("A", "0")])
    empty = batch(
        batch_id="empty", decision_at=D.replace(hour=15), valid_until=D.replace(hour=16), targets=[]
    )
    stream = history(empty, first)
    future = stream.selected_at(D - timedelta(microseconds=1))
    zero = stream.selected_at(D)
    active_empty = stream.selected_at(D.replace(hour=15))
    expired = stream.selected_at(D.replace(hour=16))
    assert (future.status, future.selected_batch, future.active_targets) == (
        TargetBatchStatus.NO_BATCH,
        None,
        (),
    )
    assert zero.status is TargetBatchStatus.ACTIVE and values(zero) == (("A", Decimal("0")),)
    assert (active_empty.status, active_empty.selected_batch, active_empty.active_targets) == (
        TargetBatchStatus.ACTIVE,
        empty,
        (),
    )
    assert (expired.status, expired.selected_batch, expired.active_targets) == (
        TargetBatchStatus.EXPIRED,
        empty,
        (),
    )
    assert history().selected_at(D).status is TargetBatchStatus.NO_BATCH


def test_latest_selected_before_expiry_never_falls_back_to_older_live_batch() -> None:
    older = batch(valid_until=D.replace(hour=18))
    newer = batch(
        batch_id="b2",
        decision_at=D.replace(hour=15),
        valid_until=D.replace(hour=16),
        targets=[proposal("A", ".05")],
    )
    stream = history(older, newer)
    assert stream.selected_at(D.replace(hour=15)).status is TargetBatchStatus.ACTIVE
    assert (
        stream.selected_at(D.replace(hour=16) - timedelta(microseconds=1)).selected_batch is newer
    )
    expired = stream.selected_at(D.replace(hour=16))
    assert expired.status is TargetBatchStatus.EXPIRED
    assert expired.selected_batch is newer and expired.active_targets == ()
    assert older.valid_until > expired.at


def test_context_half_open_boundary_and_exact_snapshot_assertions() -> None:
    supplied = batch()
    expected = context()
    assert validate_target_batch_for_context(supplied, expected, D) is None
    assert (
        validate_target_batch_for_context(
            supplied, expected, supplied.valid_until - timedelta(microseconds=1)
        )
        is None
    )
    for instant in (D - timedelta(microseconds=1), supplied.valid_until):
        with pytest.raises(ValueError, match="within"):
            validate_target_batch_for_context(supplied, expected, instant)
    # Cutoff/as-of/usable equality at decision is explicitly allowed.
    boundary = TargetSnapshotAssertion("boundary", D, D)
    at_boundary = batch(data_cutoff_at=D, data_snapshot=boundary, portfolio_snapshot=boundary)
    boundary_context = context(
        data_cutoff_at=D, data_snapshot=boundary, portfolio_snapshot=boundary
    )
    validate_target_batch_for_context(at_boundary, boundary_context, D)


@pytest.mark.parametrize(
    "changes",
    [
        {"run_id": "run-2"},
        {"strategy_id": "T"},
        {"strategy_version": "version-2"},
        {"decision_at": D + timedelta(minutes=1)},
        {
            "data_cutoff_at": CUTOFF - timedelta(minutes=1),
            "data_snapshot": replace(DATA, as_of_at=CUTOFF - timedelta(minutes=1)),
        },
        {"data_snapshot": replace(DATA, snapshot_id="other-data")},
        {"data_snapshot": replace(DATA, asserted_usable_at=D - timedelta(minutes=1))},
        {"portfolio_snapshot": replace(PORTFOLIO, snapshot_id="other-portfolio")},
        {"portfolio_snapshot": replace(PORTFOLIO, as_of_at=CUTOFF - timedelta(minutes=1))},
        {"portfolio_snapshot": replace(PORTFOLIO, asserted_usable_at=D - timedelta(minutes=1))},
    ],
)
def test_every_context_field_mismatch_rejects_without_mutation(changes: dict[str, Any]) -> None:
    supplied, expected = batch(), context(**changes)
    before = history(supplied)
    with pytest.raises(ValueError, match="differs"):
        validate_target_batch_for_context(supplied, expected, D)
    assert before.batches == (supplied,)
    assert history(supplied) == before


@pytest.mark.parametrize("constructor", [batch, context])
@pytest.mark.parametrize(
    "changes",
    [
        {"data_cutoff_at": D + timedelta(microseconds=1)},
        {"data_snapshot": replace(DATA, as_of_at=CUTOFF - timedelta(microseconds=1))},
        {"portfolio_snapshot": replace(PORTFOLIO, as_of_at=D + timedelta(microseconds=1))},
        {"data_snapshot": replace(DATA, asserted_usable_at=D + timedelta(microseconds=1))},
        {
            "portfolio_snapshot": replace(
                PORTFOLIO, asserted_usable_at=D + timedelta(microseconds=1)
            )
        },
        {"data_snapshot": "data-1"},
        {"portfolio_snapshot": None},
    ],
)
def test_snapshot_time_inconsistency_or_untyped_snapshot_rejects(
    constructor: Any, changes: dict[str, Any]
) -> None:
    with pytest.raises(ValueError):
        constructor(**changes)


def test_no_invented_snapshot_age_threshold_or_asof_usable_order() -> None:
    old = datetime(1990, 1, 1, tzinfo=UTC)
    # These are assertions; as-of may follow usable without invented source semantics.
    data = TargetSnapshotAssertion("asserted-data", CUTOFF, old)
    portfolio = TargetSnapshotAssertion("asserted-portfolio", old, old)
    supplied = batch(data_snapshot=data, portfolio_snapshot=portfolio)
    expected = context(data_snapshot=data, portfolio_snapshot=portfolio)
    validate_target_batch_for_context(supplied, expected, D)


def test_normalized_retry_retains_first_batch_and_snapshot_assertions() -> None:
    original = batch()
    offset = timezone(timedelta(hours=5, minutes=30), "reference")
    equivalent = batch(
        decision_at=D.astimezone(offset),
        valid_until=original.valid_until.astimezone(offset),
        data_cutoff_at=CUTOFF.astimezone(offset),
        data_snapshot=TargetSnapshotAssertion(
            "data-1", CUTOFF.astimezone(offset), D.astimezone(offset)
        ),
        portfolio_snapshot=TargetSnapshotAssertion(
            "portfolio-1", CUTOFF.astimezone(offset), D.astimezone(offset)
        ),
        targets=[proposal("B", ".2000"), proposal("A", ".1")],
    )
    assert equivalent == original and equivalent is not original
    stream = history(original, equivalent, original)
    assert stream.batches == (original,) and stream.batches[0] is original
    assert stream.batches[0].data_snapshot is DATA
    assert stream.batches[0].portfolio_snapshot is PORTFOLIO
    assert stream.batches[0].targets[0].equity_weight.as_tuple().exponent == -2
    validate_target_batch_for_context(equivalent, context(), D)


@pytest.mark.parametrize(
    "changes",
    [
        {"targets": [proposal("A", ".11")]},
        {"targets": []},
        {"valid_until": D.replace(hour=19)},
        {"decision_at": D + timedelta(minutes=1)},
        {
            "data_cutoff_at": CUTOFF - timedelta(minutes=1),
            "data_snapshot": replace(DATA, as_of_at=CUTOFF - timedelta(minutes=1)),
        },
        {"data_snapshot": replace(DATA, snapshot_id="other")},
        {"data_snapshot": replace(DATA, asserted_usable_at=D - timedelta(seconds=1))},
        {"portfolio_snapshot": replace(PORTFOLIO, snapshot_id="other")},
        {"portfolio_snapshot": replace(PORTFOLIO, as_of_at=CUTOFF - timedelta(seconds=1))},
        {"portfolio_snapshot": replace(PORTFOLIO, asserted_usable_at=D - timedelta(seconds=1))},
    ],
)
def test_changed_batch_id_retries_reject_and_leave_existing_history_intact(
    changes: dict[str, Any],
) -> None:
    first = batch()
    prior = history(first)
    changed = batch(**changes)
    with pytest.raises(ValueError, match="conflicting batch_id"):
        history(first, changed)
    assert prior.batches == (first,)
    assert prior.selected_at(D).selected_batch is first


@pytest.mark.parametrize(
    "field,value", [("run_id", "run-2"), ("strategy_id", "T"), ("strategy_version", "version-2")]
)
def test_stream_and_version_isolation_not_filtering(field: str, value: str) -> None:
    other = batch(**{field: value})
    with pytest.raises(ValueError, match="stream"):
        history(batch(), other)
    # Same batch IDs in independent pinned streams have independent scope.
    isolated = history(other, **{field: value})
    assert isolated.selected_at(D).selected_batch is other
    with pytest.raises(ValueError, match="stream"):
        TargetBatchSelection("run-1", "S", "version-1", D, other)


@pytest.mark.parametrize("reverse", [False, True])
def test_future_conflicts_and_same_decision_ties_reject_globally(reverse: bool) -> None:
    present = batch()
    future = batch(
        batch_id="future", decision_at=D.replace(day=3), valid_until=D.replace(day=3, hour=18)
    )
    conflict = replace(future, targets=(proposal("A", ".99"),))
    tied = replace(future, batch_id="different-id")
    for other in (conflict, tied):
        records = [present, future, other]
        if reverse:
            records.reverse()
        with pytest.raises(ValueError, match="conflicting|share a decision"):
            history(*records)
    assert history(present).selected_at(D).selected_batch is present


@pytest.mark.parametrize("role", ["data_snapshot", "portfolio_snapshot"])
@pytest.mark.parametrize("field", ["as_of_at", "asserted_usable_at"])
def test_snapshot_ids_cannot_change_metadata_even_in_unselected_future(
    role: str, field: str
) -> None:
    first = batch()
    existing = getattr(first, role)
    changed_snapshot = replace(existing, **{field: getattr(existing, field) - timedelta(minutes=1)})
    changes: dict[str, Any] = {role: changed_snapshot}
    if role == "data_snapshot" and field == "as_of_at":
        changes["data_cutoff_at"] = changed_snapshot.as_of_at
    future = batch(
        batch_id="future",
        decision_at=D.replace(day=3),
        valid_until=D.replace(day=3, hour=18),
        **changes,
    )
    # Each separate expected context is valid; collection consistency still fails.
    own_context = TargetDecisionContext(
        future.run_id,
        future.strategy_id,
        future.strategy_version,
        future.decision_at,
        future.data_cutoff_at,
        future.data_snapshot,
        future.portfolio_snapshot,
    )
    validate_target_batch_for_context(future, own_context, future.decision_at)
    for records in ([first, future], [future, first]):
        with pytest.raises(ValueError, match="snapshot_id metadata"):
            history(*records)


def test_snapshot_roles_have_separate_namespaces_and_same_metadata_can_be_reused() -> None:
    # Same exact ID with different metadata in separate roles is valid.
    data = TargetSnapshotAssertion("shared", CUTOFF, D)
    portfolio = TargetSnapshotAssertion("shared", CUTOFF - timedelta(minutes=1), D)
    first = batch(data_snapshot=data, portfolio_snapshot=portfolio)
    later = batch(
        batch_id="later",
        decision_at=D.replace(hour=15),
        data_snapshot=data,
        portfolio_snapshot=portfolio,
    )
    stream = history(later, first)
    assert stream.batches == (first, later)
    assert stream.selected_at(D.replace(hour=15)).selected_batch is later


def test_direct_selection_computes_status_but_does_not_prove_latest() -> None:
    older = batch()
    newer = batch(batch_id="new", decision_at=D.replace(hour=15), targets=[])
    query = D.replace(hour=15)
    direct = TargetBatchSelection("run-1", "S", "version-1", query, older)
    assert direct.status is TargetBatchStatus.ACTIVE and direct.selected_batch is older
    assert history(older, newer).selected_at(query).selected_batch is newer
    empty = TargetBatchSelection("run-1", "S", "version-1", query, None)
    assert empty.status is TargetBatchStatus.NO_BATCH and empty.active_targets == ()
    expired = TargetBatchSelection("run-1", "S", "version-1", older.valid_until, older)
    assert expired.status is TargetBatchStatus.EXPIRED and expired.active_targets == ()
    for changes in ({"status": TargetBatchStatus.EXPIRED}, {"active_targets": ()}):
        with pytest.raises(TypeError):
            TargetBatchSelection("run-1", "S", "version-1", query, older, **changes)  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="decision"):
        TargetBatchSelection("run-1", "S", "version-1", D - timedelta(microseconds=1), older)
    for invalid in ({}, "b1", 0):
        with pytest.raises(ValueError, match="selected_batch"):
            TargetBatchSelection("run-1", "S", "version-1", query, invalid)  # type: ignore[arg-type]
    with pytest.raises(FrozenInstanceError):
        direct.status = TargetBatchStatus.EXPIRED  # type: ignore[misc]


def test_explicit_inputs_are_snapshotted_and_frozen_without_mutating_callers() -> None:
    inputs = [proposal("B", ".20"), proposal("A", ".10")]
    first = batch(targets=inputs)
    assert tuple(p.security_id for p in inputs) == ("B", "A")
    inputs.clear()
    assert tuple(p.security_id for p in first.targets) == ("A", "B")
    records = [first]
    stream = TargetBatchHistory("run-1", "S", "version-1", records)
    records.clear()
    assert stream.batches == (first,)
    expected = context()
    for obj, field, value in (
        (first.targets[0], "equity_weight", Decimal(".9")),
        (DATA, "snapshot_id", "changed"),
        (first, "batch_id", "changed"),
        (stream, "batches", ()),
        (expected, "run_id", "changed"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(obj, field, value)
    assert validate_target_batch_for_context(first, expected, D) is None


@pytest.mark.parametrize("invalid", [None, "", {}, set(), iter(()), [None], ["A"]])
def test_target_and_history_containers_require_explicit_typed_list_or_tuple(invalid: Any) -> None:
    with pytest.raises(ValueError):
        batch(targets=invalid)
    with pytest.raises(ValueError):
        TargetBatchHistory("run-1", "S", "version-1", invalid)


def test_container_subclasses_and_duplicate_security_ids_reject() -> None:
    class Targets(list[TargetProposal]):
        pass

    class Batches(tuple[TargetBatch, ...]):
        pass

    with pytest.raises(ValueError, match="built-in"):
        batch(targets=Targets())
    with pytest.raises(ValueError, match="built-in"):
        history(batches=Batches())
    for targets in (
        [proposal("A", ".1"), proposal("A", ".1")],
        [proposal("A", ".1"), proposal("A", ".2")],
    ):
        with pytest.raises(ValueError, match="duplicate"):
            batch(targets=targets)


class DecimalSubclass(Decimal):
    pass


@pytest.mark.parametrize(
    "invalid",
    [
        True,
        False,
        0,
        1,
        0.1,
        ".1",
        None,
        Decimal("-.1"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
        DecimalSubclass(".1"),
    ],
)
def test_invalid_weights_reject_without_numeric_coercion(invalid: Any) -> None:
    # All traps expose accidental arithmetic/comparison of signaling NaNs.
    with localcontext() as decimal_context:
        for signal in decimal_context.traps:
            decimal_context.traps[signal] = True
        with pytest.raises(ValueError):
            TargetProposal("A", "equity_weight", invalid)
        assert not any(decimal_context.flags.values())


@pytest.mark.parametrize("unit", [None, "", "shares", "percent", "equity_weight ", 1])
def test_unit_is_required_and_exact(unit: Any) -> None:
    with pytest.raises(ValueError, match="unit"):
        TargetProposal("A", unit, Decimal(".1"))


def test_no_default_unit_weight_or_expiry_and_no_limits_or_percent_rescaling() -> None:
    with pytest.raises(TypeError):
        TargetProposal("A", equity_weight=Decimal(".1"))  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        TargetProposal("A", "equity_weight")  # type: ignore[call-arg]
    arguments = dict(
        run_id="run-1",
        strategy_id="S",
        strategy_version="version-1",
        batch_id="b1",
        decision_at=D,
        data_cutoff_at=CUTOFF,
        data_snapshot=DATA,
        portfolio_snapshot=PORTFOLIO,
        targets=[],
    )
    with pytest.raises(TypeError):
        TargetBatch(**arguments)  # type: ignore[arg-type]
    supplied = batch(targets=[proposal("A", "10"), proposal("B", "20")])
    assert values(history(supplied).selected_at(D)) == (("A", Decimal("10")), ("B", Decimal("20")))


def test_decimal_exactness_huge_exponents_and_ambient_precision_independence() -> None:
    exact = Decimal(".123456789012345678901234567890123456789")
    huge, tiny = Decimal("1e999999999"), Decimal("1e-999999999")
    signed_zero = Decimal("-0e999999999")
    with localcontext() as decimal_context:
        decimal_context.prec = 1
        decimal_context.Emax = 1
        decimal_context.Emin = -1
        for signal in decimal_context.traps:
            decimal_context.traps[signal] = True
        decimal_context.clear_flags()
        supplied = batch(
            targets=[
                TargetProposal("A", "equity_weight", exact),
                TargetProposal("B", "equity_weight", huge),
                TargetProposal("C", "equity_weight", tiny),
                TargetProposal("D", "equity_weight", signed_zero),
            ]
        )
        stream = history(supplied, replace(supplied, targets=tuple(reversed(supplied.targets))))
        assert len(stream.batches) == 1 and stream.batches[0] is supplied
        assert tuple(t.equity_weight for t in supplied.targets) == (exact, huge, tiny, signed_zero)
        assert supplied.targets[0].equity_weight is exact
        assert supplied.targets[-1].equity_weight.is_signed()
        assert proposal("A", ".1") == proposal("A", ".1000")
        assert proposal("A", "0") == proposal("A", "-0")
        assert not any(decimal_context.flags.values())


@pytest.mark.parametrize("invalid", [None, "", " \t", 1])
@pytest.mark.parametrize(
    "constructor",
    [
        lambda v: TargetProposal(v, "equity_weight", Decimal(".1")),
        lambda v: TargetSnapshotAssertion(v, CUTOFF, D),
        lambda v: batch(batch_id=v),
        lambda v: batch(run_id=v),
        lambda v: batch(strategy_id=v),
        lambda v: batch(strategy_version=v),
        lambda v: context(run_id=v),
        lambda v: context(strategy_id=v),
        lambda v: context(strategy_version=v),
        lambda v: TargetBatchHistory(v, "S", "version-1", []),
        lambda v: TargetBatchHistory("run-1", v, "version-1", []),
        lambda v: TargetBatchHistory("run-1", "S", v, []),
        lambda v: TargetBatchSelection(v, "S", "version-1", D, None),
        lambda v: TargetBatchSelection("run-1", v, "version-1", D, None),
        lambda v: TargetBatchSelection("run-1", "S", v, D, None),
    ],
)
def test_nonblank_typed_ids_are_required_everywhere(invalid: Any, constructor: Any) -> None:
    with pytest.raises(ValueError):
        constructor(invalid)


def test_exact_ids_keep_whitespace_and_case_with_no_ticker_inference() -> None:
    data = TargetSnapshotAssertion(" data :1 ", CUTOFF, D)
    supplied = batch(
        run_id=" run-1 ",
        strategy_id=" s ",
        strategy_version=" v ",
        batch_id=" b ",
        data_snapshot=data,
        targets=[proposal("a", ".2"), proposal(" A ", ".1")],
    )
    expected = context(
        run_id=" run-1 ", strategy_id=" s ", strategy_version=" v ", data_snapshot=data
    )
    validate_target_batch_for_context(supplied, expected, D)
    assert supplied.batch_id == " b " and data.snapshot_id == " data :1 "
    assert tuple(t.security_id for t in supplied.targets) == (" A ", "a")
    with pytest.raises(ValueError):
        validate_target_batch_for_context(supplied, replace(expected, strategy_id="s"), D)


@pytest.mark.parametrize(
    "batch_arg,context_arg", [(None, context()), (batch(), None), ({}, {}), (context(), batch())]
)
def test_context_validation_requires_typed_records(batch_arg: Any, context_arg: Any) -> None:
    with pytest.raises(ValueError):
        validate_target_batch_for_context(batch_arg, context_arg, D)


@pytest.mark.parametrize("expiry", [D, D - timedelta(microseconds=1)])
def test_expiry_must_strictly_follow_decision(expiry: datetime) -> None:
    with pytest.raises(ValueError, match="follow"):
        batch(valid_until=expiry)


class CustomZone(tzinfo):
    def utcoffset(self, value: datetime | None) -> timedelta:
        return timedelta(0)


class DateTimeSubclass(datetime):
    pass


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        date(2025, 1, 2),
        datetime(2025, 1, 2),
        DateTimeSubclass(2025, 1, 2, tzinfo=UTC),
        datetime(2025, 1, 2, tzinfo=CustomZone()),
        datetime.min.replace(tzinfo=timezone(timedelta(hours=23))),
        datetime.max.replace(tzinfo=timezone(-timedelta(hours=23))),
        datetime(2021, 3, 14, 2, 30, tzinfo=ZoneInfo("America/New_York"), fold=0),
        datetime(2021, 3, 14, 2, 30, tzinfo=ZoneInfo("America/New_York"), fold=1),
    ],
)
def test_invalid_scalar_times_reject_before_normalization(invalid: Any) -> None:
    with pytest.raises(ValueError):
        TargetSnapshotAssertion("data", invalid, D)
    with pytest.raises(ValueError):
        TargetBatchSelection("run-1", "S", "version-1", invalid, None)


@pytest.mark.parametrize(
    "boundary",
    [
        lambda t: TargetSnapshotAssertion("data", t, D),
        lambda t: TargetSnapshotAssertion("data", CUTOFF, t),
        lambda t: batch(decision_at=t),
        lambda t: batch(valid_until=t),
        lambda t: batch(data_cutoff_at=t),
        lambda t: context(decision_at=t),
        lambda t: context(data_cutoff_at=t),
        lambda t: validate_target_batch_for_context(batch(), context(), t),
        lambda t: history().selected_at(t),
        lambda t: TargetBatchSelection("run-1", "S", "version-1", t, None),
    ],
)
def test_each_public_time_boundary_rejects_naive_values(boundary: Any) -> None:
    with pytest.raises(ValueError):
        boundary(datetime(2025, 1, 2, 14))


@pytest.mark.parametrize(
    "key,name", [("No/TargetZone", "UTC"), ("America/New_York", "UTC"), ("UTC", "GMT")]
)
def test_keyed_zone_requires_reopenable_offset_and_name(key: str, name: str) -> None:
    # Independent zero-transition TZif v1; no host TZPATH fixture dependency.
    abbreviation = name.encode("ascii") + b"\0"
    tzif = (
        b"TZif\0"
        + b"\0" * 15
        + struct.pack(">6l", 0, 0, 0, 0, 1, len(abbreviation))
        + struct.pack(">lbb", 0, 0, 0)
        + abbreviation
    )
    zone = ZoneInfo.from_file(BytesIO(tzif), key=key)
    supplied = D.replace(tzinfo=zone)
    with pytest.raises(ValueError, match="key"):
        TargetSnapshotAssertion("data", supplied, D)
    with pytest.raises(ValueError, match="key"):
        history().selected_at(supplied)


def test_unkeyed_zoneinfo_is_not_supported() -> None:
    abbreviation = b"UTC\0"
    tzif = (
        b"TZif\0"
        + b"\0" * 15
        + struct.pack(">6l", 0, 0, 0, 0, 1, len(abbreviation))
        + struct.pack(">lbb", 0, 0, 0)
        + abbreviation
    )
    zone = ZoneInfo.from_file(BytesIO(tzif))
    with pytest.raises(ValueError, match="keyed ZoneInfo"):
        TargetSnapshotAssertion("data", D.replace(tzinfo=zone), D)


def test_valid_folds_compare_by_utc_instant_and_context_does_not_hide_mismatch() -> None:
    zone = ZoneInfo("America/New_York")
    first = datetime(2021, 11, 7, 1, 30, tzinfo=zone, fold=0)
    second = first.replace(fold=1)
    data = TargetSnapshotAssertion("data", first, first)
    portfolio = TargetSnapshotAssertion("portfolio", first, first)
    supplied = batch(
        decision_at=first,
        valid_until=second,
        data_cutoff_at=first,
        data_snapshot=data,
        portfolio_snapshot=portfolio,
    )
    expected = context(
        decision_at=first, data_cutoff_at=first, data_snapshot=data, portfolio_snapshot=portfolio
    )
    assert supplied.decision_at == datetime(2021, 11, 7, 5, 30, tzinfo=UTC)
    assert supplied.valid_until == datetime(2021, 11, 7, 6, 30, tzinfo=UTC)
    assert all(
        value.fold == 0 for value in (supplied.decision_at, supplied.valid_until, data.as_of_at)
    )
    validate_target_batch_for_context(supplied, expected, first)
    stream = history(supplied)
    assert stream.selected_at(first).status is TargetBatchStatus.ACTIVE
    assert stream.selected_at(second).status is TargetBatchStatus.EXPIRED
    assert (
        stream.selected_at(first.astimezone(UTC) - timedelta(microseconds=1)).status
        is TargetBatchStatus.NO_BATCH
    )
    with pytest.raises(ValueError, match="within"):
        validate_target_batch_for_context(supplied, expected, second)
    with pytest.raises(ValueError, match="data snapshot as_of_at"):
        batch(
            decision_at=second,
            valid_until=second.astimezone(UTC) + timedelta(hours=1),
            data_cutoff_at=first,
            data_snapshot=replace(data, as_of_at=second),
            portfolio_snapshot=portfolio,
        )
    assert first.fold == 0 and second.fold == 1


def test_offset_equivalence_and_same_instant_ties_are_normalized() -> None:
    offset = timezone(timedelta(hours=-3, microseconds=-123), "named exact offset")
    data = TargetSnapshotAssertion("data-1", CUTOFF.astimezone(offset), D.astimezone(offset))
    expected = context(
        decision_at=D.astimezone(offset),
        data_cutoff_at=CUTOFF.astimezone(offset),
        data_snapshot=data,
    )
    validate_target_batch_for_context(batch(), expected, D.astimezone(offset))
    tied = batch(batch_id="tie", decision_at=D.astimezone(offset))
    with pytest.raises(ValueError, match="share a decision"):
        history(batch(), tied)
    assert history(batch()).selected_at(D.replace(fold=1)).at.fold == 0


def test_source_timestamp_gate_and_operational_ingestion_remain_distinct() -> None:
    source_usable = D + timedelta(minutes=1)
    availability = InformationAvailability(
        None, D - timedelta(hours=1), source_usable, datetime(2026, 1, 1, tzinfo=UTC)
    )
    data = TargetSnapshotAssertion("caller-bound-data", CUTOFF, availability.first_usable_at)
    with pytest.raises(ValueError, match="asserted_usable_at"):
        batch(data_snapshot=data)
    supplied = batch(decision_at=source_usable, data_snapshot=data)
    expected = context(decision_at=source_usable, data_snapshot=data)
    validate_target_batch_for_context(supplied, expected, source_usable)
    assert availability.is_usable_at(source_usable)
    assert not availability.is_available_to_platform_at(
        source_usable, processed_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC)
    )
    with pytest.raises(ValueError, match="processed_at"):
        availability.is_available_to_platform_at(source_usable, processed_at=None)  # type: ignore[arg-type]
    # A false caller assertion can also pass; this API authenticates neither source nor receipt.
    false_assertion = replace(data, asserted_usable_at=D)
    validate_target_batch_for_context(
        batch(data_snapshot=false_assertion), context(data_snapshot=false_assertion), D
    )


def test_existing_replay_digest_can_be_retained_as_assertion_without_implicit_resolver(
    tmp_path: Path,
) -> None:
    archive = LocalRawArchive(tmp_path)
    fixtures = Path(__file__).parents[1] / "fixtures"
    payload = b"abc"

    archive.put(hashlib.sha256(payload).hexdigest(), payload)
    for kind in ("listing", "membership"):
        for suffix in ("receipt", "observation-record", "history-record"):
            encoded = (fixtures / f"{kind}-{suffix}-v1.json").read_bytes()
            archive.put(hashlib.sha256(encoded).hexdigest(), encoded)
    replay_digest = "36acbceb24abb1b9956e25fe59e066963d0b33559190fae4a9f76fd561d0be27"
    archive.put(replay_digest, (fixtures / "universe-listing-replay-v1.json").read_bytes())
    replay = archive.get_universe_listing_replay(replay_digest)
    decision = replay.result.membership.decision_at
    cutoff = replay.result.membership.effective_at
    # Explicit caller mapping of an existing artifact ID to an asserted snapshot timeline.
    data = TargetSnapshotAssertion(replay_digest, cutoff, decision)
    portfolio = TargetSnapshotAssertion("caller-portfolio", decision, decision)
    supplied = batch(
        decision_at=decision,
        valid_until=decision + timedelta(hours=1),
        data_cutoff_at=cutoff,
        data_snapshot=data,
        portfolio_snapshot=portfolio,
        targets=[proposal("security-1", ".1")],
    )
    expected = context(
        decision_at=decision,
        data_cutoff_at=cutoff,
        data_snapshot=data,
        portfolio_snapshot=portfolio,
    )
    for path in tmp_path.iterdir():
        path.unlink()
    validate_target_batch_for_context(supplied, expected, decision)
    assert supplied.data_snapshot.snapshot_id == replay_digest
    assert history(supplied).selected_at(decision).active_targets == (proposal("security-1", ".1"),)
    # No target resolver reopens the archive, proves snapshot availability or validates membership.
