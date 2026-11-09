# Architecture (initial contract)

**Status:** design baseline, not implemented services. Review changes through ADRs.

## Mission
Long-lived, research-first U.S. equities platform for swing strategies and eventually paper/live execution. The platform is a **modular Python monolith** with narrow contracts, not a distributed system.

## Module ownership
- `core`: aware timestamps, identifiers, immutable domain contracts.
- `data`: ingestion, security master, corporate actions, point-in-time sources, lineage.
- `research`: feature computation, experiment metadata, validation, immutable results.
- `backtest`: deterministic event scheduling, fill simulation, accounting, costs.
- `strategies`: pure strategy functions from available observations to desired exposures.
- `intelligence`: macro, company events, SEC filings, later licensed alternative data.
- `portfolio`: account constraints, net exposures, candidate allocations, deterministic risk vetoes.
- `execution`: future paper/live adapters, order idempotency, reconciliation, safety stop.

## Dependency direction
- `core` imports no platform modules.
- `data` and `intelligence` depend on `core`, not on trading execution.
- `strategies` depend on stable domain contracts, not broker SDKs, databases, or web calls.
- `research` and `backtest` compose data, strategies, and domain contracts.
- `portfolio` consumes targets and known account state; never trusts a model's self-reported limits.
- `execution` accepts only pre-vetted orders. Research agents have no order permissions.
- Avoid cycles. An adapter may translate external records into core contracts; core never imports adapters.

## Data and replay
Store immutable raw snapshots separately from normalized curated datasets. Preserve source, revision/version, licensing, and temporal provenance. For historically valid simulation distinguish *first usable publication/source availability* from when the platform backfilled the record. Decisions must have a timestamp. Timezone-aware datetimes are mandatory.

Initial analytical storage: Parquet + DuckDB; operational PostgreSQL is deferred until there is a real need for persistent order state. An experiment must pin code revision, configuration, source snapshot identifiers, seeds, and a complete [execution environment](environment.md). A code revision or seed alone is insufficient for replay.

Data adapters distinguish quarantined raw records from validated availability. Historical replay uses proven public/provider availability; operational consumers additionally require actual ingestion and completed processing. Derived features must validate every input and model artifact against the decision cutoff. See [data contracts](data-contracts.md) for mode, revision, and lineage rules.

`data.admission` implements only the in-memory raw availability boundary: frozen
source claims produce accepted UTC timestamps or a quarantine result retaining
the raw envelope and field-specific reasons. Evidence references are adapter
assertions, not authenticated proof; quarantine has no durable storage. Provider
ingestion and operational processing remain unimplemented. See
[ADR 0006](decisions/0006-raw-availability-admission.md).

Research registration and holdout consumption follow the [research protocol](research-protocol.md). These remain design contracts until M3 implements their persistent enforcement. Target exposures follow the [strategy contract](strategy-contract.md); portfolio conversion and accounting remain unimplemented.

## Execution boundary
Research, paper, and eventual live modes share strategy logic and risk policy contracts but **do not share credentials, mutable account state, or unapproved deployment paths**. Live mode does not exist in the scaffold. A future live implementation needs explicit owner authorization, external reconciliation, independent kill switch, and negative-path tests.

## Design exclusions in this scaffold
No broker calls; no order router; no strategy profitability claims; no LLM jobs; no satellite processing; no artificial enterprise service boundaries. New subsystems require a measured reason.
