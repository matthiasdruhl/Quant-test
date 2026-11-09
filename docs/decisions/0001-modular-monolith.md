# ADR 0001: Modular Python monolith

- **Status:** Accepted for initial scaffold
- **Date:** 2026-11-09

## Context
A solo-maintained, long-term quantitative research platform needs correctness, transparent interfaces, and reproducible testing more than distributed scaling.

## Decision
Use one installable Python package with bounded subpackages: core, data, research, backtest, strategies, intelligence, portfolio, and execution. Use Parquet/DuckDB for future historical analytics; add persistent operational storage only when required. Future UI is optional and separate.

## Alternatives considered
- Microservices: independent deployment but high operational and cross-service consistency overhead.
- Multiple repos: improved repository isolation but unnecessary coordination and versioning cost.
- Custom distributed backtester: complexity without measured requirements.

## Consequences
Fast tests, auditable dependency graph, easy local replay, simple onboarding. This requires discipline around internal interfaces. Split services only when instrumented bottlenecks or security isolation needs justify it, with a new ADR.
