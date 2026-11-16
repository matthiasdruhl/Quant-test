"""Pure explicit-fill reference accounting under approved ADR0017 v1.

Inputs are accounting assertions, not actual fills or authenticated market data.
No calendar, simulator, target conversion, persistence, broker or order path exists.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from zoneinfo import ZoneInfo


def _text(value: object, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be standard nonblank text")
    return value


def _integer(value: object, name: str, *, positive: bool = False) -> int:
    if type(value) is not int or value < (1 if positive else 0):
        qualifier = "positive" if positive else "nonnegative"
        raise ValueError(f"{name} must be a standard {qualifier} integer")
    return value


def _utc_instant(value: datetime, name: str) -> datetime:
    if type(value) is not datetime:
        raise ValueError(f"{name} must be a standard datetime")
    zone = value.tzinfo
    if zone is UTC or type(zone) is timezone:
        pass
    elif type(zone) is ZoneInfo and isinstance(zone.key, str):
        try:
            replayed = value.replace(tzinfo=ZoneInfo(zone.key))
        except (KeyError, ValueError) as error:
            raise ValueError(f"{name} requires a reopenable ZoneInfo key") from error
        if replayed.utcoffset() != value.utcoffset() or replayed.tzname() != value.tzname():
            raise ValueError(f"{name} ZoneInfo key does not reproduce zone rules")
    else:
        raise ValueError(f"{name} requires UTC, timezone or keyed ZoneInfo")
    if value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    try:
        utc = value.astimezone(UTC)
        roundtrip = utc.astimezone(zone)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{name} cannot be represented as a UTC instant") from error
    if (
        roundtrip.replace(tzinfo=None) != value.replace(tzinfo=None)
        or roundtrip.utcoffset() != value.utcoffset()
    ):
        raise ValueError(f"{name} is a nonexistent local time")
    return utc.replace(fold=0)


def _event_instant(event_id: str, occurred_at: datetime, reference_id: str) -> datetime:
    _text(event_id, "event_id")
    _text(reference_id, "reference_id")
    return _utc_instant(occurred_at, "occurred_at")


@dataclass(frozen=True, slots=True)
class OpeningCashEvent:
    """One explicit currency/hundredth opening, with zero initial positions."""

    event_id: str
    occurred_at: datetime
    reference_id: str
    currency: str
    money_unit: str
    settled_cash_hundredths: int

    def __post_init__(self) -> None:
        instant = _event_instant(self.event_id, self.occurred_at, self.reference_id)
        _text(self.currency, "currency")
        if type(self.money_unit) is not str or self.money_unit != "currency_hundredth":
            raise ValueError("money_unit must be explicitly currency_hundredth")
        _integer(self.settled_cash_hundredths, "settled_cash_hundredths")
        object.__setattr__(self, "occurred_at", instant)


@dataclass(frozen=True, slots=True)
class FillEvent:
    """An explicit whole-share fill assertion; no execution or price inference."""

    event_id: str
    occurred_at: datetime
    reference_id: str
    fill_id: str
    security_id: str
    side: str
    quantity_shares: int
    unit_price_hundredths: int
    fee_hundredths: int
    currency: str

    def __post_init__(self) -> None:
        instant = _event_instant(self.event_id, self.occurred_at, self.reference_id)
        _text(self.fill_id, "fill_id")
        _text(self.security_id, "security_id")
        _text(self.currency, "currency")
        if type(self.side) is not str or self.side not in ("buy", "sell"):
            raise ValueError("side must be exactly buy or sell")
        _integer(self.quantity_shares, "quantity_shares", positive=True)
        _integer(self.unit_price_hundredths, "unit_price_hundredths", positive=True)
        _integer(self.fee_hundredths, "fee_hundredths")
        object.__setattr__(self, "occurred_at", instant)


@dataclass(frozen=True, slots=True)
class SettlementEvent:
    """Settle one entire known open fill; no supplied amount or inferred due date."""

    event_id: str
    occurred_at: datetime
    reference_id: str
    fill_id: str

    def __post_init__(self) -> None:
        instant = _event_instant(self.event_id, self.occurred_at, self.reference_id)
        _text(self.fill_id, "fill_id")
        object.__setattr__(self, "occurred_at", instant)


LedgerEvent = OpeningCashEvent | FillEvent | SettlementEvent


@dataclass(frozen=True, slots=True)
class ValuationMark:
    """One same-instant explicit price/currency assertion, including zero."""

    security_id: str
    valued_at: datetime
    unit_price_hundredths: int
    currency: str
    reference_id: str

    def __post_init__(self) -> None:
        _text(self.security_id, "security_id")
        _text(self.currency, "currency")
        _text(self.reference_id, "reference_id")
        _integer(self.unit_price_hundredths, "unit_price_hundredths")
        object.__setattr__(self, "valued_at", _utc_instant(self.valued_at, "valued_at"))


@dataclass(frozen=True, slots=True)
class PositionBalance:
    """Immutable output row; cannot be supplied as ledger initial state."""

    security_id: str
    held_quantity_shares: int
    unsettled_buy_quantity_shares: int
    sellable_quantity_shares: int = field(init=False)

    def __post_init__(self) -> None:
        _text(self.security_id, "security_id")
        held = _integer(self.held_quantity_shares, "held_quantity_shares", positive=True)
        unsettled = _integer(self.unsettled_buy_quantity_shares, "unsettled_buy_quantity_shares")
        if unsettled > held:
            raise ValueError("Unsettled buys exceed held shares")
        object.__setattr__(self, "sellable_quantity_shares", held - unsettled)


@dataclass(frozen=True, slots=True, init=False)
class ReferenceLedger:
    """All state derives from a nonempty explicit event stream, never injected totals."""

    events: tuple[LedgerEvent, ...]
    event_ids: tuple[str, ...]
    settled_fill_ids: tuple[str, ...]
    open_fills: tuple[FillEvent, ...]
    last_event_at: datetime
    currency: str
    money_unit: str
    settled_cash_hundredths: int
    buy_payables_hundredths: int
    sale_receivables_hundredths: int
    available_cash_hundredths: int
    positions: tuple[PositionBalance, ...]

    def __init__(self, events: tuple[LedgerEvent, ...] | list[LedgerEvent]) -> None:
        if type(events) not in (tuple, list) or not events:
            raise ValueError("events must be an explicit nonempty built-in tuple or list")
        supplied = tuple(events)
        if any(
            type(event) not in (OpeningCashEvent, FillEvent, SettlementEvent) for event in supplied
        ):
            raise ValueError("events must contain exact supported ledger event types")
        if type(supplied[0]) is not OpeningCashEvent:
            raise ValueError("The first distinct event must be opening cash")
        opening = supplied[0]
        # The first-type guard above is deliberately exact; narrow for typed replay.
        assert isinstance(opening, OpeningCashEvent)
        cash, payables, receivables = opening.settled_cash_hundredths, 0, 0
        held: dict[str, int] = {}
        unsettled: dict[str, int] = {}
        applied: dict[str, LedgerEvent] = {}
        fills: dict[str, FillEvent] = {}
        open_fills: dict[str, FillEvent] = {}
        settled_ids: set[str] = set()
        last = opening.occurred_at
        for event in supplied:
            previous = applied.get(event.event_id)
            if previous is not None:
                if previous != event:
                    raise ValueError("Conflicting event_id retry")
                continue  # Identity precedes time, repeated opening and closed-fill checks.
            if event.occurred_at < last:
                raise ValueError("New events must be in nondecreasing time order")
            if type(event) is OpeningCashEvent:
                if applied:
                    raise ValueError("Opening cash cannot recur under a new event ID")
            elif type(event) is FillEvent:
                if event.currency != opening.currency:
                    raise ValueError("Fill currency differs from declared ledger currency")
                if event.fill_id in fills:
                    raise ValueError("Fill ID must be unique forever")
                quantity = event.quantity_shares
                gross = quantity * event.unit_price_hundredths
                security = event.security_id
                if event.side == "buy":
                    obligation = gross + event.fee_hundredths
                    if obligation > cash - payables:
                        raise ValueError("Buy exceeds available settled cash")
                    held[security] = held.get(security, 0) + quantity
                    unsettled[security] = unsettled.get(security, 0) + quantity
                    payables += obligation
                else:
                    if quantity > held.get(security, 0) - unsettled.get(security, 0):
                        raise ValueError("Sale exceeds sellable settled shares")
                    if event.fee_hundredths > gross:
                        raise ValueError("Sale fee exceeds gross proceeds")
                    held[security] -= quantity
                    receivables += gross - event.fee_hundredths
                fills[event.fill_id] = event
                open_fills[event.fill_id] = event
            else:
                assert type(event) is SettlementEvent
                fill = open_fills.get(event.fill_id)
                if fill is None:
                    raise ValueError("Settlement requires a known open fill")
                if event.occurred_at < fill.occurred_at:
                    raise ValueError("Settlement cannot precede its fill")
                gross = fill.quantity_shares * fill.unit_price_hundredths
                if fill.side == "buy":
                    obligation = gross + fill.fee_hundredths
                    cash -= obligation
                    payables -= obligation
                    unsettled[fill.security_id] -= fill.quantity_shares
                else:
                    net = gross - fill.fee_hundredths
                    cash += net
                    receivables -= net
                del open_fills[event.fill_id]
                settled_ids.add(event.fill_id)
            # All validations above precede accepting the event identity/cursor.
            applied[event.event_id] = event
            last = event.occurred_at
        if any(not held[security] >= unsettled.get(security, 0) >= 0 for security in held):
            raise ValueError("Ledger held/unsettled share invariants failed")
        positions = tuple(
            PositionBalance(security, held[security], unsettled.get(security, 0))
            for security in sorted(held)
            if held[security] > 0
        )
        if not cash >= payables >= 0 or receivables < 0:
            raise ValueError("Ledger cash/obligation invariants failed")
        object.__setattr__(self, "events", tuple(applied.values()))
        object.__setattr__(self, "event_ids", tuple(applied))
        object.__setattr__(self, "settled_fill_ids", tuple(sorted(settled_ids)))
        object.__setattr__(
            self, "open_fills", tuple(open_fills[name] for name in sorted(open_fills))
        )
        object.__setattr__(self, "last_event_at", last)
        object.__setattr__(self, "currency", opening.currency)
        object.__setattr__(self, "money_unit", opening.money_unit)
        object.__setattr__(self, "settled_cash_hundredths", cash)
        object.__setattr__(self, "buy_payables_hundredths", payables)
        object.__setattr__(self, "sale_receivables_hundredths", receivables)
        object.__setattr__(self, "available_cash_hundredths", cash - payables)
        object.__setattr__(self, "positions", positions)

    def apply(self, event: LedgerEvent) -> "ReferenceLedger":
        """Return a new full replay, or this exact ledger for an identical retry."""
        replayed = ReferenceLedger((*self.events, event))
        return self if replayed.events == self.events else replayed

    def value_at(
        self, at: datetime, marks: tuple[ValuationMark, ...] | list[ValuationMark]
    ) -> "LedgerValuation":
        """Require fresh same-instant marks; valuation changes no ledger state."""
        return LedgerValuation(self, at, marks)


@dataclass(frozen=True, slots=True, init=False)
class LedgerValuation:
    """Arithmetic valuation only; every amount derives from ledger plus exact marks."""

    ledger: ReferenceLedger
    at: datetime
    marks: tuple[ValuationMark, ...]
    marked_holdings_hundredths: int
    equity_hundredths: int

    def __init__(
        self,
        ledger: ReferenceLedger,
        at: datetime,
        marks: tuple[ValuationMark, ...] | list[ValuationMark],
    ) -> None:
        if type(ledger) is not ReferenceLedger:
            raise ValueError("ledger must be an exact ReferenceLedger")
        instant = _utc_instant(at, "at")
        if instant < ledger.last_event_at:
            raise ValueError("Valuation must not precede last accepted event")
        if type(marks) not in (tuple, list):
            raise ValueError("marks must be an explicit built-in tuple or list")
        supplied = tuple(marks)
        if any(type(mark) is not ValuationMark for mark in supplied):
            raise ValueError("marks must contain exact ValuationMark records")
        prices: dict[str, int] = {}
        for mark in supplied:
            if mark.security_id in prices:
                raise ValueError("Duplicate valuation security_id")
            if mark.currency != ledger.currency:
                raise ValueError("Mark currency differs from declared ledger currency")
            if mark.valued_at != instant:
                raise ValueError("Mark instant differs from valuation instant")
            prices[mark.security_id] = mark.unit_price_hundredths
        if set(prices) != {position.security_id for position in ledger.positions}:
            raise ValueError("Mark set must exactly match positive held securities")
        marked = sum(
            position.held_quantity_shares * prices[position.security_id]
            for position in ledger.positions
        )
        equity = (
            ledger.settled_cash_hundredths
            + ledger.sale_receivables_hundredths
            - ledger.buy_payables_hundredths
            + marked
        )
        object.__setattr__(self, "ledger", ledger)
        object.__setattr__(self, "at", instant)
        object.__setattr__(
            self, "marks", tuple(sorted(supplied, key=lambda mark: mark.security_id))
        )
        object.__setattr__(self, "marked_holdings_hundredths", marked)
        object.__setattr__(self, "equity_hundredths", equity)
