"""Approved v1 independent integer references and immutable rejection boundaries.

Fills/marks are explicit reference assertions, not provider data, actual account
activity or strategy performance. Expected state/equity literals predate runtime.
"""

import struct
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from quant_test.backtest.reference_ledger import (
    FillEvent,
    LedgerValuation,
    OpeningCashEvent,
    PositionBalance,
    ReferenceLedger,
    SettlementEvent,
    ValuationMark,
)
from quant_test.core.time import InformationAvailability
from quant_test.strategies.targets import TargetProposal


def instant(hour: int, minute: int = 0, *, day: int = 2) -> datetime:
    return datetime(2025, 1, day, hour, minute, tzinfo=UTC)


def opening(scenario: str = "s1", cash: int = 100000) -> OpeningCashEvent:
    return OpeningCashEvent(
        f"{scenario}/open",
        instant(9),
        f"reference/{scenario}/open",
        "USD",
        "currency_hundredth",
        cash,
    )


def fill(
    scenario: str = "s1",
    fill_id: str = "B1",
    *,
    at: datetime | None = None,
    side: str = "buy",
    quantity: int = 10,
    price: int = 2000,
    fee: int = 100,
    security: str = "A",
    currency: str = "USD",
) -> FillEvent:
    return FillEvent(
        f"{scenario}/fill/{fill_id}",
        instant(10) if at is None else at,
        f"reference/{scenario}/fill/{fill_id}",
        fill_id,
        security,
        side,
        quantity,
        price,
        fee,
        currency,
    )


def settlement(
    scenario: str = "s1", fill_id: str = "B1", *, at: datetime | None = None
) -> SettlementEvent:
    return SettlementEvent(
        f"{scenario}/settle/{fill_id}",
        instant(11) if at is None else at,
        f"reference/{scenario}/settle/{fill_id}",
        fill_id,
    )


def mark(
    scenario: str,
    at: datetime,
    price: int,
    *,
    security: str = "A",
    currency: str = "USD",
    label: str | None = None,
) -> ValuationMark:
    time = at.isoformat().replace("+00:00", "Z")
    return ValuationMark(
        security,
        at,
        price,
        currency,
        f"valuation/{scenario}/{time}/{price if label is None else label}",
    )


def settled_s1() -> ReferenceLedger:
    return ReferenceLedger([opening(), fill(), settlement()])


def state(ledger: ReferenceLedger) -> tuple[Any, ...]:
    return (
        ledger.settled_cash_hundredths,
        ledger.buy_payables_hundredths,
        ledger.sale_receivables_hundredths,
        ledger.available_cash_hundredths,
        tuple(
            (
                p.security_id,
                p.held_quantity_shares,
                p.unsettled_buy_quantity_shares,
                p.sellable_quantity_shares,
            )
            for p in ledger.positions
        ),
        tuple(f.fill_id for f in ledger.open_fills),
        ledger.settled_fill_ids,
    )


def test_approved_scenario_1_buy_fee_recognition_and_full_settlement() -> None:
    opened = ReferenceLedger([opening()])
    bought = opened.apply(fill())
    assert state(bought) == (100000, 20100, 0, 79900, (("A", 10, 10, 0),), ("B1",), ())
    at = instant(10, 30)
    assert bought.value_at(at, [mark("s1", at, 2000)]).equity_hundredths == 99900
    assert bought.value_at(at, [mark("s1", at, 2200)]).equity_hundredths == 101900
    settled = bought.apply(settlement())
    assert state(settled) == (79900, 0, 0, 79900, (("A", 10, 0, 10),), (), ("B1",))
    assert settled.value_at(instant(11), [mark("s1", instant(11), 2000)]).equity_hundredths == 99900
    assert (
        settled.value_at(instant(11), [mark("s1", instant(11), 2200)]).equity_hundredths == 101900
    )
    assert bought.open_fills == (fill(),)
    assert opened.events == (opening(),) and opened.positions == ()


def test_approved_scenario_2_distinct_partial_fills_costs_and_settlements() -> None:
    first_sale = fill("s2", "S1", at=instant(12), side="sell", quantity=4, price=2500, fee=50)
    second_sale = fill("s2", "S2", at=instant(12, 1), side="sell", quantity=2, price=2400, fee=25)
    ledger = settled_s1().apply(first_sale).apply(second_sale)
    assert state(ledger) == (79900, 0, 14725, 79900, (("A", 4, 0, 4),), ("S1", "S2"), ("B1",))
    at = instant(12, 2)
    value = ledger.value_at(at, [mark("s2", at, 2400)])
    assert value.marked_holdings_hundredths == 9600 and value.equity_hundredths == 104225
    settled_first = ledger.apply(settlement("s2", "S1", at=instant(11, day=3)))
    assert state(settled_first) == (89850, 0, 4775, 89850, (("A", 4, 0, 4),), ("S2",), ("B1", "S1"))
    at = instant(11, day=3)
    assert settled_first.value_at(at, [mark("s2", at, 2400)]).equity_hundredths == 104225
    settled_both = settled_first.apply(settlement("s2", "S2", at=instant(11, 1, day=3)))
    assert state(settled_both) == (94625, 0, 0, 94625, (("A", 4, 0, 4),), (), ("B1", "S1", "S2"))
    at = instant(11, 1, day=3)
    assert settled_both.value_at(at, [mark("s2", at, 2400)]).equity_hundredths == 104225


def test_approved_scenario_3_reservation_and_unsettled_share_rejection() -> None:
    first = fill("s3", "B1", quantity=6, price=1000, fee=100)
    ledger = ReferenceLedger([opening("s3", 10000), first])
    assert state(ledger) == (10000, 6100, 0, 3900, (("A", 6, 6, 0),), ("B1",), ())
    bad = fill("s3", "B2-bad", at=instant(10, 1), quantity=4, price=1000, fee=0)
    with pytest.raises(ValueError, match="available settled cash"):
        ledger.apply(bad)
    assert bad.event_id not in ledger.event_ids and bad.fill_id not in tuple(
        f.fill_id for f in ledger.open_fills
    )
    second = fill("s3", "B2", at=instant(10, 2), quantity=3, price=1000, fee=0)
    both = ledger.apply(second)
    assert state(both) == (10000, 9100, 0, 900, (("A", 9, 9, 0),), ("B1", "B2"), ())
    with pytest.raises(ValueError, match="sellable"):
        both.apply(
            fill("s3", "early-sale", at=instant(10, 3), side="sell", quantity=1, price=1000, fee=0)
        )
    at = instant(10, 3)
    assert both.value_at(at, [mark("s3", at, 1000)]).equity_hundredths == 9900
    settled_first = both.apply(settlement("s3", "B1"))
    assert state(settled_first) == (3900, 3000, 0, 900, (("A", 9, 3, 6),), ("B2",), ("B1",))
    with pytest.raises(ValueError, match="sellable"):
        settled_first.apply(
            fill("s3", "seven-sale", at=instant(11), side="sell", quantity=7, price=1000, fee=0)
        )
    at = instant(11)
    assert settled_first.value_at(at, [mark("s3", at, 1000)]).equity_hundredths == 9900


def test_approved_scenario_4_event_identity_and_settlement_conflicts() -> None:
    ledger = settled_s1()
    assert ledger.apply(fill()) is ledger and ledger.apply(settlement()) is ledger
    assert ledger.last_event_at == instant(11)
    at = instant(11, 1)
    assert ledger.value_at(at, [mark("s4", at, 2000)]).equity_hundredths == 99900
    for rejected in (
        replace(fill(), unit_price_hundredths=2100),
        replace(fill(), event_id="s4/duplicate-fill", reference_id="reference/s4/duplicate-fill"),
        SettlementEvent(
            "s4/duplicate-settlement", instant(11), "reference/s4/duplicate-settlement", "B1"
        ),
        SettlementEvent(
            "s4/unknown-settlement", instant(11), "reference/s4/unknown-settlement", "unknown"
        ),
    ):
        with pytest.raises(ValueError):
            ledger.apply(rejected)
        assert state(ledger) == (79900, 0, 0, 79900, (("A", 10, 0, 10),), (), ("B1",))


def test_approved_scenario_5_equal_time_order_and_invalid_valuation_requests() -> None:
    first = fill("s5", "B1", quantity=2, price=1000, fee=0)
    ledger = ReferenceLedger([opening("s5", 10000), first])
    assert state(ledger) == (10000, 2000, 0, 8000, (("A", 2, 2, 0),), ("B1",), ())
    sale = fill("s5", "S1", at=instant(11), side="sell", quantity=1, price=1200, fee=0)
    with pytest.raises(ValueError, match="sellable"):
        ledger.apply(sale)
    at = instant(11)
    assert ledger.value_at(at, [mark("s5", at, 1200)]).equity_hundredths == 10400
    settled = ledger.apply(settlement("s5"))
    assert state(settled) == (8000, 0, 0, 8000, (("A", 2, 0, 2),), (), ("B1",))
    assert settled.value_at(at, [mark("s5", at, 1200)]).equity_hundredths == 10400
    sold = settled.apply(sale)
    assert state(sold) == (8000, 0, 1200, 8000, (("A", 1, 0, 1),), ("S1",), ("B1",))
    assert sold.value_at(at, [mark("s5", at, 1200)]).equity_hundredths == 10400
    for marks in ([], [mark("s5", instant(11) + timedelta(seconds=1), 1200)]):
        with pytest.raises(ValueError):
            sold.value_at(at, marks)
    assert sold.last_event_at == at


def test_full_replay_determinism_identity_before_time_and_retained_first_assertion() -> None:
    events = [opening(), fill(), settlement()]
    ledger = ReferenceLedger(events)
    offset = timezone(timedelta(hours=5, minutes=30), "reference")
    retried_fill = replace(fill(), occurred_at=fill().occurred_at.astimezone(offset))
    retried_open = replace(opening(), occurred_at=opening().occurred_at.astimezone(offset))
    replayed = ReferenceLedger([*events, retried_fill, retried_open, settlement()])
    assert replayed == ledger and replayed.events == tuple(events)
    assert replayed.events[0] is events[0] and replayed.events[1] is events[1]
    assert ledger.apply(retried_open) is ledger
    assert ledger.event_ids == ("s1/open", "s1/fill/B1", "s1/settle/B1")
    assert ledger.last_event_at == instant(11)
    with pytest.raises(ValueError, match="Conflicting event_id"):
        ledger.apply(replace(fill(), reference_id="changed old reference"))


@pytest.mark.parametrize(
    "changes",
    [
        {"occurred_at": instant(8)},
        {"reference_id": "other"},
        {"currency": "usd"},
        {"settled_cash_hundredths": 99999},
    ],
)
def test_every_opening_identity_field_conflict_precedes_time_or_reopening(
    changes: dict[str, Any],
) -> None:
    ledger = settled_s1()
    with pytest.raises(ValueError, match="Conflicting event_id"):
        ledger.apply(replace(opening(), **changes))
    assert ledger == settled_s1()


@pytest.mark.parametrize(
    "changes",
    [
        {"occurred_at": instant(8)},
        {"reference_id": "other"},
        {"fill_id": "other"},
        {"security_id": "other"},
        {"side": "sell"},
        {"quantity_shares": 11},
        {"unit_price_hundredths": 2100},
        {"fee_hundredths": 0},
        {"currency": "usd"},
    ],
)
def test_every_fill_identity_field_conflict_precedes_new_event_validation(
    changes: dict[str, Any],
) -> None:
    ledger = settled_s1()
    with pytest.raises(ValueError, match="Conflicting event_id"):
        ledger.apply(replace(fill(), **changes))
    assert ledger.last_event_at == instant(11)


@pytest.mark.parametrize(
    "changes",
    [
        {"occurred_at": instant(8)},
        {"reference_id": "other"},
        {"fill_id": "other"},
    ],
)
def test_every_settlement_identity_field_conflict_precedes_closed_fill_validation(
    changes: dict[str, Any],
) -> None:
    ledger = settled_s1()
    with pytest.raises(ValueError, match="Conflicting event_id"):
        ledger.apply(replace(settlement(), **changes))
    assert ledger.open_fills == ()


@pytest.mark.parametrize(
    "collision",
    [
        lambda: replace(fill(), event_id="s1/open"),
        lambda: replace(settlement(), event_id="s1/fill/B1"),
        lambda: replace(opening(), event_id="s1/settle/B1", occurred_at=instant(12)),
    ],
)
def test_event_ids_are_global_across_event_types(collision: Any) -> None:
    with pytest.raises(ValueError, match="Conflicting event_id"):
        settled_s1().apply(collision())


def test_rejected_cash_event_ids_can_be_reused_and_all_original_state_is_immutable() -> None:
    ledger = ReferenceLedger([opening("s3", 10000), fill("s3", quantity=6, price=1000, fee=100)])
    before = state(ledger), ledger.events, ledger.event_ids, ledger.last_event_at
    invalid = fill("s3", "B2-bad", at=instant(10, 1), quantity=4, price=1000, fee=0)
    with pytest.raises(ValueError):
        ledger.apply(invalid)
    corrected = replace(invalid, quantity_shares=3)
    accepted = ledger.apply(corrected)
    assert corrected.event_id in accepted.event_ids
    assert accepted.buy_payables_hundredths == 9100 and accepted.available_cash_hundredths == 900
    assert (state(ledger), ledger.events, ledger.event_ids, ledger.last_event_at) == before
    with pytest.raises(ValueError):
        ReferenceLedger([*ledger.events, invalid, corrected])
    assert (state(ledger), ledger.events, ledger.event_ids, ledger.last_event_at) == before


def test_cash_reservations_span_securities_and_unsettled_proceeds_are_not_spendable() -> None:
    ledger = ReferenceLedger(
        [opening("reference", 10000), fill("reference", quantity=6, price=1000, fee=100)]
    )
    other = fill("reference", "B2", at=instant(10, 1), quantity=4, price=1000, fee=0, security="B")
    with pytest.raises(ValueError, match="available"):
        ledger.apply(other)
    accepted = ledger.apply(replace(other, quantity_shares=3))
    assert state(accepted) == (
        10000,
        9100,
        0,
        900,
        (("A", 6, 6, 0), ("B", 3, 3, 0)),
        ("B1", "B2"),
        (),
    )
    sold = settled_s1().apply(
        fill("reference", "S1", at=instant(12), side="sell", quantity=10, price=10000, fee=0)
    )
    assert state(sold) == (79900, 0, 100000, 79900, (), ("S1",), ("B1",))
    with pytest.raises(ValueError, match="available"):
        sold.apply(
            fill("reference", "B2", at=instant(12), quantity=8, price=10000, fee=0, security="B")
        )


def test_zero_net_sale_is_retained_until_explicit_settlement_and_requires_no_mark_after_full_sale() -> (
    None
):
    ledger = ReferenceLedger(
        [opening("zero", 100), fill("zero", quantity=1, price=100, fee=0), settlement("zero")]
    )
    sale = fill("zero", "S1", at=instant(12), side="sell", quantity=1, price=100, fee=100)
    sold = ledger.apply(sale)
    assert state(sold) == (0, 0, 0, 0, (), ("S1",), ("B1",))
    assert sold.open_fills == (sale,)
    assert sold.value_at(instant(12), []).equity_hundredths == 0
    settled = sold.apply(settlement("zero", "S1", at=instant(13)))
    assert state(settled) == (0, 0, 0, 0, (), (), ("B1", "S1"))
    assert settled.value_at(instant(13), ()).equity_hundredths == 0
    assert settled.apply(settlement("zero", "S1", at=instant(13))) is settled
    with pytest.raises(ValueError):
        settled.apply(SettlementEvent("second", instant(13), "reference/second", "S1"))


def test_sale_fee_exceeding_gross_and_short_sale_fail_without_consuming_ids() -> None:
    ledger = settled_s1()
    invalid = fill("reject", "S1", at=instant(12), side="sell", quantity=1, price=100, fee=101)
    with pytest.raises(ValueError, match="fee exceeds"):
        ledger.apply(invalid)
    accepted = ledger.apply(replace(invalid, fee_hundredths=100))
    assert accepted.open_fills == (replace(invalid, fee_hundredths=100),)
    with pytest.raises(ValueError, match="sellable"):
        ledger.apply(
            fill("reject", "S2", at=instant(12), side="sell", quantity=11, price=100, fee=0)
        )
    with pytest.raises(ValueError, match="sellable"):
        ledger.apply(
            fill(
                "reject",
                "S3",
                at=instant(12),
                side="sell",
                quantity=1,
                price=100,
                fee=0,
                security="unknown",
            )
        )


def test_first_event_later_opening_unknown_settlement_and_new_event_order_fail() -> None:
    for events in ([fill()], [settlement()], [fill(), opening()]):
        with pytest.raises(ValueError, match="first distinct"):
            ReferenceLedger(events)
    ledger = settled_s1()
    with pytest.raises(ValueError, match="Opening cash cannot recur"):
        ledger.apply(replace(opening(), event_id="new-opening", occurred_at=instant(12)))
    with pytest.raises(ValueError, match="nondecreasing"):
        ledger.apply(fill("late", "late-buy", at=instant(10, 30), quantity=1, price=100, fee=0))
    with pytest.raises(ValueError, match="known open"):
        ReferenceLedger([opening(), settlement()])
    with pytest.raises(ValueError):
        ReferenceLedger([opening(), fill(), settlement(at=instant(9, 30))])
    with pytest.raises(ValueError, match="unique forever"):
        ledger.apply(replace(fill(), event_id="new-same-fill", occurred_at=instant(12)))
    assert ledger == settled_s1()


def test_valuation_marks_are_explicit_sorted_snapshots_and_all_totals_are_derived() -> None:
    events = [
        opening("two", 200),
        fill("two", "B1", quantity=1, price=100, fee=0),
        fill("two", "B2", at=instant(10, 1), quantity=1, price=50, fee=0, security="B"),
    ]
    ledger = ReferenceLedger(events)
    at = instant(12)
    marks = [mark("two", at, 200, security="B"), mark("two", at, 300)]
    value = LedgerValuation(ledger, at, marks)
    assert value.ledger is ledger
    assert tuple(m.security_id for m in value.marks) == ("A", "B")
    assert value.marked_holdings_hundredths == 500 and value.equity_hundredths == 550
    marks.clear()
    events.clear()
    assert len(value.marks) == 2 and len(ledger.events) == 3
    assert ledger.last_event_at == instant(10, 1)
    assert (
        ledger.value_at(
            at, [mark("two", at, 0), mark("two", at, 0, security="B")]
        ).equity_hundredths
        == 50
    )
    assert value.equity_hundredths == 550
    with pytest.raises(TypeError):
        ReferenceLedger(ledger.events, settled_cash_hundredths=999999)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        LedgerValuation(ledger, at, value.marks, equity_hundredths=999999)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        PositionBalance("A", 1, 0, sellable_quantity_shares=100)  # type: ignore[call-arg]
    for record, name, changed in (
        (ledger, "settled_cash_hundredths", 99999),
        (value, "equity_hundredths", 99999),
        (ledger.positions[0], "held_quantity_shares", 99),
        (value.marks[0], "unit_price_hundredths", 99),
        (ledger.events[0], "event_id", "changed"),
    ):
        with pytest.raises(FrozenInstanceError):
            setattr(record, name, changed)


def test_valuation_does_not_advance_cursor_register_ids_cache_marks_or_settle_obligations() -> None:
    bought = ReferenceLedger([opening(), fill()])
    future = datetime(2030, 1, 1, tzinfo=UTC)
    value = bought.value_at(future, [mark("reference", future, 2000)])
    assert value.equity_hundredths == 99900
    assert bought.last_event_at == instant(10) and bought.buy_payables_hundredths == 20100
    settled = bought.apply(settlement(at=instant(10)))
    valued = settled.value_at(instant(12), [mark("reference", instant(12), 2000)])
    sold = settled.apply(
        fill("reference", "S1", at=instant(11), side="sell", quantity=1, price=2000, fee=0)
    )
    assert sold.last_event_at == instant(11) and valued.ledger.last_event_at == instant(10)
    assert sold.sale_receivables_hundredths == 2000
    assert "valuation/reference/2025-01-02T12:00:00Z/2000" not in sold.event_ids
    with pytest.raises(ValueError, match="exactly match"):
        settled.value_at(instant(12), [])
    with pytest.raises(ValueError, match="instant differs"):
        settled.value_at(instant(12, 1), list(valued.marks))


@pytest.mark.parametrize("kind", ["missing", "duplicate", "extra", "currency", "future", "past"])
def test_invalid_complete_mark_sets_do_not_mutate_ledger(kind: str) -> None:
    ledger = settled_s1()
    at = instant(12)
    marks = [mark("reference", at, 2000)]
    if kind == "missing":
        marks = []
    elif kind == "duplicate":
        marks.append(marks[0])
    elif kind == "extra":
        marks.append(mark("reference", at, 1, security="B"))
    elif kind == "currency":
        marks = [replace(marks[0], currency="usd")]
    elif kind == "future":
        marks = [replace(marks[0], valued_at=at + timedelta(microseconds=1))]
    else:
        marks = [replace(marks[0], valued_at=at - timedelta(microseconds=1))]
    before = state(ledger), ledger.event_ids, ledger.last_event_at
    with pytest.raises(ValueError):
        ledger.value_at(at, marks)
    assert (state(ledger), ledger.event_ids, ledger.last_event_at) == before
    with pytest.raises(ValueError, match="must not precede"):
        ledger.value_at(instant(10), [mark("reference", instant(10), 2000)])


def test_zero_opening_zero_mark_zero_equity_and_explicit_empty_mark_set_are_valid() -> None:
    zero = ReferenceLedger([opening("zero", 0)])
    assert state(zero) == (0, 0, 0, 0, (), (), ())
    assert zero.value_at(instant(9), []).equity_hundredths == 0
    with pytest.raises(ValueError, match="available"):
        zero.apply(fill("zero", quantity=1, price=1, fee=0))
    held = ReferenceLedger([opening("zero", 100), fill("zero", quantity=1, price=100, fee=0)])
    assert held.value_at(instant(10), [mark("zero", instant(10), 0)]).equity_hundredths == 0
    with pytest.raises(ValueError, match="exactly match"):
        held.value_at(instant(10), [])
    with pytest.raises(ValueError, match="exactly match"):
        zero.value_at(instant(9), [mark("zero", instant(9), 0)])


def test_required_units_fee_currency_and_quantities_have_no_implicit_defaults() -> None:
    with pytest.raises(TypeError):
        OpeningCashEvent("id", instant(9), "ref", "USD", settled_cash_hundredths=0)  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        FillEvent("id", instant(10), "ref", "B", "A", "buy", 1, 100, currency="USD")  # type: ignore[call-arg]
    for unit in ("", None, "cents", "currency_hundredth ", 100):
        with pytest.raises(ValueError, match="money_unit"):
            replace(opening(), money_unit=unit)
    for side in ("", None, "BUY", "sell ", 0):
        with pytest.raises(ValueError, match="side"):
            replace(fill(), side=side)
    with pytest.raises(ValueError, match="currency"):
        ReferenceLedger([opening(), replace(fill(), currency="EUR")])


class IntegerSubclass(int):
    pass


@pytest.mark.parametrize(
    "invalid", [True, False, 1.0, "1", Decimal("1"), IntegerSubclass(1), None, -1]
)
@pytest.mark.parametrize(
    "constructor",
    [
        lambda value: replace(opening(), settled_cash_hundredths=value),
        lambda value: replace(fill(), quantity_shares=value),
        lambda value: replace(fill(), unit_price_hundredths=value),
        lambda value: replace(fill(), fee_hundredths=value),
        lambda value: mark("type", instant(12), value),
    ],
)
def test_numeric_fields_require_standard_nonnegative_or_positive_ints(
    invalid: Any, constructor: Any
) -> None:
    with pytest.raises(ValueError):
        constructor(invalid)


@pytest.mark.parametrize("field", ["quantity_shares", "unit_price_hundredths"])
def test_fill_quantity_and_unit_price_must_be_strictly_positive(field: str) -> None:
    with pytest.raises(ValueError):
        replace(fill(), **{field: 0})


@pytest.mark.parametrize("invalid", [None, "", " \t", 1])
@pytest.mark.parametrize(
    "constructor",
    [
        lambda v: replace(opening(), event_id=v),
        lambda v: replace(opening(), reference_id=v),
        lambda v: replace(opening(), currency=v),
        lambda v: replace(fill(), event_id=v),
        lambda v: replace(fill(), reference_id=v),
        lambda v: replace(fill(), fill_id=v),
        lambda v: replace(fill(), security_id=v),
        lambda v: replace(fill(), currency=v),
        lambda v: replace(settlement(), event_id=v),
        lambda v: replace(settlement(), reference_id=v),
        lambda v: replace(settlement(), fill_id=v),
        lambda v: ValuationMark(v, instant(12), 1, "USD", "ref"),
        lambda v: ValuationMark("A", instant(12), 1, v, "ref"),
        lambda v: ValuationMark("A", instant(12), 1, "USD", v),
    ],
)
def test_text_identity_fields_are_exact_nonblank_strings(invalid: Any, constructor: Any) -> None:
    with pytest.raises(ValueError):
        constructor(invalid)


class StringSubclass(str):
    pass


def test_exact_text_keeps_case_spaces_and_punctuation_without_currency_or_ticker_inference() -> (
    None
):
    supplied = replace(opening(), event_id=" open:1 ", reference_id=" ref:1 ", currency=" USD ")
    bought = replace(
        fill(), event_id=" fill:1 ", fill_id=" fill:A ", security_id=" a :1 ", currency=" USD "
    )
    ledger = ReferenceLedger([supplied, bought])
    assert ledger.currency == " USD " and ledger.event_ids == (" open:1 ", " fill:1 ")
    assert ledger.positions[0].security_id == " a :1 "
    assert ledger.open_fills[0].fill_id == " fill:A "
    with pytest.raises(ValueError, match="currency"):
        ledger.value_at(instant(10), [mark("exact", instant(10), 2000, security=" a :1 ")])
    with pytest.raises(ValueError):
        replace(opening(), event_id=StringSubclass("id"))


@pytest.mark.parametrize("invalid", [None, "", {}, set(), iter(()), [], ()])
def test_ledger_requires_nonempty_explicit_container(invalid: Any) -> None:
    with pytest.raises(ValueError):
        ReferenceLedger(invalid)


@pytest.mark.parametrize("invalid", [None, "", {}, set(), iter(()), [None], [fill()]])
def test_mark_container_must_be_explicit_and_typed_even_when_empty(invalid: Any) -> None:
    with pytest.raises(ValueError):
        ReferenceLedger([opening()]).value_at(instant(9), invalid)


def test_container_and_record_subclasses_are_not_accepted_state_inputs() -> None:
    class Events(list[Any]):
        pass

    class Marks(tuple[Any, ...]):
        pass

    class OpeningSubclass(OpeningCashEvent):
        pass

    class FillSubclass(FillEvent):
        pass

    class SettlementSubclass(SettlementEvent):
        pass

    class MarkSubclass(ValuationMark):
        pass

    class LedgerSubclass(ReferenceLedger):
        pass

    with pytest.raises(ValueError):
        ReferenceLedger(Events([opening()]))
    with pytest.raises(ValueError):
        ReferenceLedger([opening()]).value_at(instant(9), Marks())
    unsupported = [
        OpeningSubclass("open", instant(9), "ref", "USD", "currency_hundredth", 100000),
        FillSubclass("fill", instant(10), "ref", "B1", "A", "buy", 1, 1, 0, "USD"),
        SettlementSubclass("settle", instant(11), "ref", "B1"),
    ]
    for event in unsupported:
        with pytest.raises(ValueError, match="exact supported"):
            settled_s1().apply(event)
    with pytest.raises(ValueError, match="exact ValuationMark"):
        settled_s1().value_at(instant(12), [MarkSubclass("A", instant(12), 1, "USD", "ref")])
    with pytest.raises(ValueError, match="exact ReferenceLedger"):
        LedgerValuation(LedgerSubclass([opening()]), instant(9), [])
    for invalid in ([None], ["event"], [PositionBalance("A", 1, 0)]):
        with pytest.raises(ValueError):
            ReferenceLedger(invalid)


def test_input_event_lists_are_snapshotted_without_reordering_equal_time_events() -> None:
    opened, bought, settled = opening(), fill(), settlement(at=instant(10))
    inputs = [opened, bought, settled]
    ledger = ReferenceLedger(inputs)
    inputs.clear()
    assert ledger.events == (opened, bought, settled)
    assert ledger.events[1] is bought and ledger.events[2] is settled
    with pytest.raises(ValueError, match="known open"):
        ReferenceLedger([opened, settled, bought])


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
def test_invalid_scalar_times_and_civil_gaps_reject_before_normalization(invalid: Any) -> None:
    with pytest.raises(ValueError):
        replace(opening(), occurred_at=invalid)
    with pytest.raises(ValueError):
        settled_s1().value_at(invalid, [])


@pytest.mark.parametrize(
    "constructor",
    [
        lambda value: replace(opening(), occurred_at=value),
        lambda value: replace(fill(), occurred_at=value),
        lambda value: replace(settlement(), occurred_at=value),
        lambda value: ValuationMark("A", value, 1, "USD", "ref"),
        lambda value: LedgerValuation(settled_s1(), value, []),
    ],
)
def test_every_public_time_boundary_rejects_naive_values(constructor: Any) -> None:
    with pytest.raises(ValueError):
        constructor(datetime(2025, 1, 2, 12))


@pytest.mark.parametrize(
    "key,name", [("No/Such_Ledger_Zone", "UTC"), ("America/New_York", "UTC"), ("UTC", "GMT")]
)
def test_keyed_zone_must_reproduce_original_offset_and_name(key: str, name: str) -> None:
    abbreviation = name.encode("ascii") + b"\0"
    tzif = (
        b"TZif\0"
        + b"\0" * 15
        + struct.pack(">6l", 0, 0, 0, 0, 1, len(abbreviation))
        + struct.pack(">lbb", 0, 0, 0)
        + abbreviation
    )
    zone = ZoneInfo.from_file(BytesIO(tzif), key=key)
    with pytest.raises(ValueError, match="key"):
        replace(fill(), occurred_at=instant(10).replace(tzinfo=zone))
    with pytest.raises(ValueError, match="key"):
        mark("zone", instant(12).replace(tzinfo=zone), 100)


def test_unkeyed_zoneinfo_rejects_at_new_reference_boundary() -> None:
    tzif = (
        b"TZif\0"
        + b"\0" * 15
        + struct.pack(">6l", 0, 0, 0, 0, 1, 4)
        + struct.pack(">lbb", 0, 0, 0)
        + b"UTC\0"
    )
    zone = ZoneInfo.from_file(BytesIO(tzif))
    with pytest.raises(ValueError, match="keyed ZoneInfo"):
        replace(opening(), occurred_at=instant(9).replace(tzinfo=zone))


def test_real_folds_order_identity_and_mark_correspondence_use_utc_instants() -> None:
    zone = ZoneInfo("America/New_York")
    first = datetime(2021, 11, 7, 1, 30, tzinfo=zone, fold=0)
    second = first.replace(fold=1)
    opened = replace(opening(), occurred_at=datetime(2021, 11, 7, 5, tzinfo=UTC))
    bought = replace(fill(), occurred_at=first)
    settled = replace(settlement(), occurred_at=second)
    ledger = ReferenceLedger([opened, bought, settled])
    assert ledger.events[1].occurred_at == datetime(2021, 11, 7, 5, 30, tzinfo=UTC)
    assert ledger.last_event_at == datetime(2021, 11, 7, 6, 30, tzinfo=UTC)
    assert all(event.occurred_at.fold == 0 for event in ledger.events)
    assert ledger.apply(replace(bought, occurred_at=first.astimezone(UTC))) is ledger
    with pytest.raises(ValueError, match="Conflicting event_id"):
        ledger.apply(replace(bought, occurred_at=second))
    with pytest.raises(ValueError, match="nondecreasing"):
        ReferenceLedger([replace(opened, occurred_at=second), bought])
    with pytest.raises(ValueError, match="instant differs"):
        ledger.value_at(second, [mark("fold", first, 2000)])
    assert ledger.value_at(second, [mark("fold", second, 2000)]).equity_hundredths == 99900
    assert first.fold == 0 and second.fold == 1


def test_offset_equivalent_marks_and_queries_normalize_without_mutating_assertions() -> None:
    ledger = settled_s1()
    offset = timezone(timedelta(hours=-3, microseconds=-123), "named exact offset")
    at = instant(12)
    value = ledger.value_at(at.astimezone(offset), [mark("offset", at.astimezone(offset), 2000)])
    assert value.at == at and value.marks[0].valued_at == at
    assert value.equity_hundredths == 99900
    folded = replace(opening(), occurred_at=instant(9).replace(fold=1))
    assert folded.occurred_at.fold == 0


def test_stable_position_open_fill_and_settled_id_order_without_event_sorting() -> None:
    bought_b = fill("order", "Z", quantity=1, price=100, fee=0, security="B")
    bought_a = fill("order", "A", quantity=1, price=100, fee=0, security="A")
    ledger = ReferenceLedger([opening("order", 200), bought_b, bought_a])
    assert ledger.events[1:] == (bought_b, bought_a)
    assert tuple(row.security_id for row in ledger.positions) == ("A", "B")
    assert tuple(event.fill_id for event in ledger.open_fills) == ("A", "Z")
    settled = ledger.apply(settlement("order", "Z")).apply(settlement("order", "A"))
    assert settled.settled_fill_ids == ("A", "Z")
    assert settled.events[-2].fill_id == "Z" and settled.events[-1].fill_id == "A"  # type: ignore[union-attr]
    assert settled.available_cash_hundredths == 0
    with pytest.raises(TypeError):
        SettlementEvent("partial", instant(12), "ref", "A", quantity_shares=1)  # type: ignore[call-arg]


def test_sellable_inventory_is_partitioned_by_stable_security_id() -> None:
    ledger = ReferenceLedger(
        [
            opening("securities", 1000),
            fill("securities", "A1", quantity=2, price=100, fee=0),
            settlement("securities", "A1", at=instant(10)),
            fill("securities", "B1", at=instant(11), quantity=1, price=100, fee=0, security="B"),
        ]
    )
    assert tuple((p.security_id, p.sellable_quantity_shares) for p in ledger.positions) == (
        ("A", 2),
        ("B", 0),
    )
    with pytest.raises(ValueError, match="sellable"):
        ledger.apply(
            fill(
                "securities",
                "B-sale",
                at=instant(12),
                side="sell",
                quantity=1,
                price=100,
                fee=0,
                security="B",
            )
        )
    sold = ledger.apply(
        fill("securities", "A-sale", at=instant(12), side="sell", quantity=2, price=100, fee=0)
    )
    assert tuple(p.security_id for p in sold.positions) == ("B",)


def test_reference_facts_are_not_actual_source_availability_or_target_conversion() -> None:
    unavailable = InformationAvailability(
        None, instant(10, day=3), instant(11, day=3), instant(12, day=3)
    )
    asserted_fill = fill()
    assert not unavailable.is_usable_at(asserted_fill.occurred_at)
    ledger = ReferenceLedger([opening(), asserted_fill])
    assert ledger.positions[0].held_quantity_shares == 10
    # Ledger accepts supplied accounting assertions; it never authenticates this source.
    target = TargetProposal("A", "equity_weight", Decimal(".1"))
    with pytest.raises(ValueError, match="exact supported"):
        ledger.apply(target)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="standard positive integer"):
        replace(asserted_fill, quantity_shares=target.equity_weight)
    zero = ReferenceLedger([opening("zero", 0)])
    assert zero.value_at(instant(9), []).equity_hundredths == 0
    assert target.equity_weight == Decimal(".1")  # No conversion or order permission follows.
