"""Immutable long-only equity-fraction assertions and pure lifecycle selection.

Snapshot and decision timelines are caller assertions, not authenticated data,
current account state or operational receipt proof. No allocation or orders exist.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")
    return value


def _stream(run_id: str, strategy_id: str, strategy_version: str) -> tuple[str, str, str]:
    return (
        _text(run_id, "run_id"),
        _text(strategy_id, "strategy_id"),
        _text(strategy_version, "strategy_version"),
    )


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


@dataclass(frozen=True, slots=True)
class TargetProposal:
    """A desired final equity fraction, without sizing, limits or permission."""

    security_id: str
    unit: str
    equity_weight: Decimal

    def __post_init__(self) -> None:
        _text(self.security_id, "security_id")
        if not isinstance(self.unit, str) or self.unit != "equity_weight":
            raise ValueError("unit must be explicitly equity_weight")
        value = self.equity_weight
        if type(value) is not Decimal or not value.is_finite():
            raise ValueError("equity_weight must be a standard finite nonnegative Decimal")
        # No Decimal arithmetic, rounding or context-sensitive normalization.
        if value.is_signed() and not value.is_zero():
            raise ValueError("equity_weight must be nonnegative in this long-only boundary")


@dataclass(frozen=True, slots=True)
class TargetSnapshotAssertion:
    """Exact caller-asserted identity, as-of instant and usable instant; no proof."""

    snapshot_id: str
    as_of_at: datetime
    asserted_usable_at: datetime

    def __post_init__(self) -> None:
        _text(self.snapshot_id, "snapshot_id")
        object.__setattr__(self, "as_of_at", _utc_instant(self.as_of_at, "as_of_at"))
        object.__setattr__(
            self, "asserted_usable_at", _utc_instant(self.asserted_usable_at, "asserted_usable_at")
        )


def _validate_snapshots(
    decision_at: datetime,
    data_cutoff_at: datetime,
    data_snapshot: TargetSnapshotAssertion,
    portfolio_snapshot: TargetSnapshotAssertion,
) -> None:
    if not isinstance(data_snapshot, TargetSnapshotAssertion) or not isinstance(
        portfolio_snapshot, TargetSnapshotAssertion
    ):
        raise ValueError("snapshots must be TargetSnapshotAssertion records")
    if data_cutoff_at > decision_at:
        raise ValueError("data_cutoff_at must not follow decision_at")
    if data_snapshot.as_of_at != data_cutoff_at:
        raise ValueError("data snapshot as_of_at must equal data_cutoff_at")
    if portfolio_snapshot.as_of_at > decision_at:
        raise ValueError("portfolio snapshot as_of_at must not follow decision_at")
    if (
        data_snapshot.asserted_usable_at > decision_at
        or portfolio_snapshot.asserted_usable_at > decision_at
    ):
        raise ValueError("snapshot asserted_usable_at must not follow decision_at")


def _targets(
    values: tuple[TargetProposal, ...] | list[TargetProposal],
) -> tuple[TargetProposal, ...]:
    if type(values) not in (tuple, list):
        raise ValueError("targets must be an explicit built-in tuple or list")
    records = tuple(values)
    if any(not isinstance(record, TargetProposal) for record in records):
        raise ValueError("targets must contain TargetProposal records")
    if len({record.security_id for record in records}) != len(records):
        raise ValueError("duplicate target security_id")
    return tuple(sorted(records, key=lambda record: record.security_id))


@dataclass(frozen=True, slots=True, init=False)
class TargetBatch:
    """One complete replacement for a run/strategy/version, with asserted context."""

    run_id: str
    strategy_id: str
    strategy_version: str
    batch_id: str
    decision_at: datetime
    valid_until: datetime
    data_cutoff_at: datetime
    data_snapshot: TargetSnapshotAssertion
    portfolio_snapshot: TargetSnapshotAssertion
    targets: tuple[TargetProposal, ...]

    def __init__(
        self,
        run_id: str,
        strategy_id: str,
        strategy_version: str,
        batch_id: str,
        decision_at: datetime,
        valid_until: datetime,
        data_cutoff_at: datetime,
        data_snapshot: TargetSnapshotAssertion,
        portfolio_snapshot: TargetSnapshotAssertion,
        targets: tuple[TargetProposal, ...] | list[TargetProposal],
    ) -> None:
        _stream(run_id, strategy_id, strategy_version)
        _text(batch_id, "batch_id")
        decision = _utc_instant(decision_at, "decision_at")
        expiry = _utc_instant(valid_until, "valid_until")
        cutoff = _utc_instant(data_cutoff_at, "data_cutoff_at")
        _validate_snapshots(decision, cutoff, data_snapshot, portfolio_snapshot)
        if decision >= expiry:
            raise ValueError("valid_until must follow decision_at")
        proposals = _targets(targets)
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "strategy_version", strategy_version)
        object.__setattr__(self, "batch_id", batch_id)
        object.__setattr__(self, "decision_at", decision)
        object.__setattr__(self, "valid_until", expiry)
        object.__setattr__(self, "data_cutoff_at", cutoff)
        object.__setattr__(self, "data_snapshot", data_snapshot)
        object.__setattr__(self, "portfolio_snapshot", portfolio_snapshot)
        object.__setattr__(self, "targets", proposals)


@dataclass(frozen=True, slots=True)
class TargetDecisionContext:
    """Expected full caller context, not an authenticated snapshot/current account."""

    run_id: str
    strategy_id: str
    strategy_version: str
    decision_at: datetime
    data_cutoff_at: datetime
    data_snapshot: TargetSnapshotAssertion
    portfolio_snapshot: TargetSnapshotAssertion

    def __post_init__(self) -> None:
        _stream(self.run_id, self.strategy_id, self.strategy_version)
        decision = _utc_instant(self.decision_at, "decision_at")
        cutoff = _utc_instant(self.data_cutoff_at, "data_cutoff_at")
        _validate_snapshots(decision, cutoff, self.data_snapshot, self.portfolio_snapshot)
        object.__setattr__(self, "decision_at", decision)
        object.__setattr__(self, "data_cutoff_at", cutoff)


def validate_target_batch_for_context(
    batch: TargetBatch, context: TargetDecisionContext, at: datetime
) -> None:
    """Match full expected assertions and half-open eligibility, without mutation."""
    if not isinstance(batch, TargetBatch) or not isinstance(context, TargetDecisionContext):
        raise ValueError("batch and context must be typed target records")
    instant = _utc_instant(at, "at")
    for name in (
        "run_id",
        "strategy_id",
        "strategy_version",
        "decision_at",
        "data_cutoff_at",
        "data_snapshot",
        "portfolio_snapshot",
    ):
        if getattr(batch, name) != getattr(context, name):
            raise ValueError(f"batch {name} differs from expected context")
    if not batch.decision_at <= instant < batch.valid_until:
        raise ValueError("query must be within [decision_at, valid_until)")


class TargetBatchStatus(StrEnum):
    """Lifecycle output for an asserted timeline, not operational arrival state."""

    NO_BATCH = "NO_BATCH"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class TargetBatchSelection:
    """Consistent selected provenance; direct construction does not prove latest."""

    run_id: str
    strategy_id: str
    strategy_version: str
    at: datetime
    selected_batch: TargetBatch | None
    status: TargetBatchStatus = field(init=False)
    active_targets: tuple[TargetProposal, ...] = field(init=False)

    def __post_init__(self) -> None:
        expected_stream = _stream(self.run_id, self.strategy_id, self.strategy_version)
        instant = _utc_instant(self.at, "at")
        selected = self.selected_batch
        if selected is None:
            status = TargetBatchStatus.NO_BATCH
        else:
            if not isinstance(selected, TargetBatch):
                raise ValueError("selected_batch must be a TargetBatch or None")
            if (
                selected.run_id,
                selected.strategy_id,
                selected.strategy_version,
            ) != expected_stream:
                raise ValueError("selected batch differs from selection stream")
            if selected.decision_at > instant:
                raise ValueError("selected batch decision must not follow query")
            status = (
                TargetBatchStatus.ACTIVE
                if instant < selected.valid_until
                else TargetBatchStatus.EXPIRED
            )
        object.__setattr__(self, "at", instant)
        object.__setattr__(self, "status", status)
        object.__setattr__(
            self,
            "active_targets",
            selected.targets if selected is not None and status is TargetBatchStatus.ACTIVE else (),
        )


@dataclass(frozen=True, slots=True, init=False)
class TargetBatchHistory:
    """Globally validated complete assertions for one exact stream, not arrivals."""

    run_id: str
    strategy_id: str
    strategy_version: str
    batches: tuple[TargetBatch, ...]

    def __init__(
        self,
        run_id: str,
        strategy_id: str,
        strategy_version: str,
        batches: tuple[TargetBatch, ...] | list[TargetBatch],
    ) -> None:
        expected_stream = _stream(run_id, strategy_id, strategy_version)
        if type(batches) not in (tuple, list):
            raise ValueError("batches must be an explicit built-in tuple or list")
        records = tuple(batches)
        if any(not isinstance(record, TargetBatch) for record in records):
            raise ValueError("batches must contain TargetBatch records")
        by_id: dict[str, TargetBatch] = {}
        decisions: set[datetime] = set()
        data_snapshots: dict[str, TargetSnapshotAssertion] = {}
        portfolio_snapshots: dict[str, TargetSnapshotAssertion] = {}
        for record in records:
            if (record.run_id, record.strategy_id, record.strategy_version) != expected_stream:
                raise ValueError("batch differs from pinned history stream")
            previous = by_id.get(record.batch_id)
            if previous is not None:
                if previous != record:
                    raise ValueError("conflicting batch_id retry")
                continue
            if record.decision_at in decisions:
                raise ValueError("distinct batch IDs cannot share a decision instant")
            for snapshot, known in (
                (record.data_snapshot, data_snapshots),
                (record.portfolio_snapshot, portfolio_snapshots),
            ):
                prior = known.get(snapshot.snapshot_id)
                if prior is not None and prior != snapshot:
                    raise ValueError("snapshot_id metadata changed within its role")
                known[snapshot.snapshot_id] = snapshot
            by_id[record.batch_id] = record
            decisions.add(record.decision_at)
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "strategy_id", strategy_id)
        object.__setattr__(self, "strategy_version", strategy_version)
        object.__setattr__(
            self, "batches", tuple(sorted(by_id.values(), key=lambda record: record.decision_at))
        )

    def selected_at(self, at: datetime) -> TargetBatchSelection:
        """Select latest asserted decision first, then expiry; never fall back."""
        instant = _utc_instant(at, "at")
        selected = next(
            (batch for batch in reversed(self.batches) if batch.decision_at <= instant), None
        )
        return TargetBatchSelection(
            self.run_id, self.strategy_id, self.strategy_version, instant, selected
        )
