# Testing and verification plan

## Fast checks
CI runs `ruff check .`, `ruff format --check .`, `mypy src`, and `pytest` on a fixed supported Python version.

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
Only timestamp availability logic has a tiny implemented test suite. All other classes, backtest correctness, and financial invariants remain **unimplemented** and must not be marked complete.

## Pull request acceptance
- Small, coherent task and explicit non-goals.
- Tests covering normal and failure modes.
- Logs of checks actually run.
- Migration/ADR for public contract changes.
- Benchmark or profiling evidence before performance abstractions.
- Human approval for financial conventions, dependencies, and any eventual brokerage access.
