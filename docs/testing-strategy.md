# Testing and verification plan

## Fast checks
CI is configured to run `ruff check .`, `ruff format --check .`, `mypy src`, and `pytest` on the exact Python baseline in `.python-version`, on Ubuntu and macOS. It additionally builds/installs a wheel and checks that the data/time modules import; pytest then exercises the installed distribution. Local checks use the same hash-locked installation described in [environment setup](environment.md). A workflow file is not evidence of a successful remote run.

## Test layers
1. **Unit:** deterministic parsers, timestamps, calculations, validation, negative paths.
2. **Contract:** provider/strategy/portfolio interfaces and hand-calculated accounting fixtures.
3. **Property:** monotonicity/invariants using Hypothesis; random valid and invalid sequences.
4. **Integration:** data ingestion → as-of features → strategy → simulated order → ledger.
5. **Adversarial:** look-ahead traps, delayed releases, delistings, zero volume, holidays, splits, duplicated fills, reconnects, partial fills.
6. **Research:** out-of-sample stability, baselines, fees, market-regime comparisons, multiple-hypothesis selection controls.

## Independent evidence
Reference fixtures must be constructed from an external calculation or human-readable specification, not copied from implementation results. A separate reviewer checks the acceptance contract and can add failing cases. Do not weaken a test merely to make a PR pass.

## Scope of current scaffold
Timestamp availability and in-memory historical observation-version selection have implemented test suites. They cover release boundaries, missing/naive timestamps, revisions, ambiguous ordering, offsets, future announced events, and actual platform ingestion/processing boundaries for the timestamp primitive. Adapters must still prove provenance and implement raw quarantine. Effective-dated joins, derived lineage, target processing, holdout access control, backtest correctness, and financial invariants remain **unimplemented** and must not be marked complete.

Before M1 acceptance, independent cases must exercise unknown availability quarantine, revisions, effective-dated mappings, and universe joins. Before M3 acceptance, exercise [target reference cases](decisions/0004-target-exposures.md), future-trained artifacts and preprocessors, and [holdout lifecycle failures](research-protocol.md). Before M7 acceptance, prove operational consumers cannot fall back to historical-only availability or bypass the independent risk gate. Documented scenarios must become executable tests in the owning milestone; prose alone does not satisfy these gates.

## Pull request acceptance
- Small, coherent task and explicit non-goals.
- Tests covering normal and failure modes.
- Logs of checks actually run.
- Migration/ADR for public contract changes.
- Benchmark or profiling evidence before performance abstractions.
- Human approval for financial conventions, dependencies, and any eventual brokerage access.
