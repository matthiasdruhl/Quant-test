# Documentation audit — 2026-11-09

## Scope and baseline

Reviewed all 25 tracked Markdown files against source, tests, fixtures, package
metadata, the dependency/toolchain lock inputs, ignore rules and CI configuration
at revision
[`f9a49d8c8a8bca55bccb5c1a1a0678f31747d54c`](https://github.com/matthiasdruhl/Quant-test/commit/f9a49d8c8a8bca55bccb5c1a1a0678f31747d54c),
plus the documentation corrections in this working tree. Source and verification
script docstrings were also inspected. This is a documentation audit, with no
product behavior, public API, dependencies, financial conventions, milestone
approval, or repository settings changed.

## Findings and corrections

| Finding | Correction and evidence |
| --- | --- |
| The README still described the original scaffold and its directory map did not distinguish planned modules. Its CI wording omitted the completed M0 evidence. | Updated [README](../README.md) to describe active M1 primitives and raw storage, label planned modules and the reserved integration directory, and link the existing M0 evidence. Six future packages contain only docstrings; `core.time` and seven `data` modules contain the implementations. |
| Architecture and data-contract headings presented implemented APIs as only a design baseline/draft; planned analytical storage was easy to confuse with current storage. | Updated [architecture](architecture.md) and [data contracts](data-contracts.md) to distinguish implemented primitives from future contracts. Parquet/DuckDB remain planned; `pyproject.toml` declares no runtime dependencies. |
| Earlier ADR exclusions could be read as current repository-wide limitations after later slices added joins, persistence and reports. | Added subsequent-extension notes to [ADR 0005](decisions/0005-observation-revision-selection.md), [ADR 0006](decisions/0006-raw-availability-admission.md), [ADR 0009](decisions/0009-local-raw-payload-archive.md) and [ADR 0010](decisions/0010-persisted-raw-admission-receipts.md). Original slice scope and review status are preserved. |
| ADR 0009 incorrectly grouped filesystem-invalid roots under `ValueError`. | Corrected it and the current data contracts: invalid root argument type/shape raises `ValueError`; missing, non-directory, symlinked or inaccessible roots raise `ArchiveIOError`. Reference cases are `test_invalid_root_input_rejects`, `test_root_must_exist_and_be_a_directory` and `test_root_symlink_and_symlink_ancestor_reject` in [archive tests](../tests/contract/test_raw_archive.py). |
| The testing plan listed future layers without identifying which exist. | Updated [testing strategy](testing-strategy.md): unit/contract suites exist, cross-module and adversarial cases live in contract tests, the integration directory has only `.gitkeep`, and no Hypothesis property suite exists yet. |
| The roadmap described implemented slices without linking their latest merged verification. | Marked M1 explicitly active and added exact-revision CI evidence in the [roadmap](roadmap.md#m1--point-in-time-market-data). All five M1 gates remain open. |
| The `data` package docstring described only in-memory contracts. | Updated the [package docstring](../src/quant_test/data/__init__.py) to include local raw archives and receipts. |

## Coverage of unchanged documents

These files were reviewed and required no content correction:

| Documents | Comparison |
| --- | --- |
| [Agent instructions](../AGENTS.md), [security boundary](../SECURITY.md), [PR template](../.github/pull_request_template.md) | Still applicable: research-only scope, provenance, explicit approval boundaries and required quality checks agree with the implementation and workflow. |
| [Invariants](invariants.md), [research protocol](research-protocol.md), [risk policy](risk-policy.md), [strategy contract](strategy-contract.md) | Correctly distinguish intended properties and future enforcement from implemented timestamp/data checks. No strategy, target processor, experiment registry, ledger or execution adapter exists. |
| [Environment](environment.md) | Python 3.11.17, uv 0.13.5, installation flags, lock inputs, platform matrix and hash-verification procedure match `.python-version`, the workflow and verification script. |
| [M0 evidence](m0-evidence.md) | Dated historical evidence, including the original hash-verification limitation, is preserved. GitHub still reports both jobs successful for correction run 42694728391. Historical test counts describe those revisions, not today's suite. |
| [ADR 0001](decisions/0001-modular-monolith.md), [0002](decisions/0002-information-eligibility.md), [0003](decisions/0003-reproducible-environments.md), [0004](decisions/0004-target-exposures.md) | Monolith, timestamp modes and environment decisions match current code/configuration; strategy target semantics remain explicitly design-only. |
| [ADR 0007](decisions/0007-historical-security-listings.md), [0008](decisions/0008-point-in-time-universe-membership.md) | Complete replacement histories, stable IDs, effective/decision cutoffs, negative provenance, unresolved joins and DST checks match implementation and reference tests. |
| [ADR 0011](decisions/0011-raw-receipt-set-quality-report.md) | Receipt identity denominator, strict codecs, recomputed reports, dependency-first publication and failure limits match implementation and the literal schema fixture. |

## Verification

Local commands ran in the existing `.venv`, activated with
`source .venv/bin/activate`, on macOS with CPython 3.11.17 and uv 0.13.5:

| Command/check | Observed result |
| --- | --- |
| `ruff check .` | All checks passed. |
| `ruff format --check .` | 54 files already formatted, including this report. |
| `mypy src` | No issues in 17 source files. |
| `pytest` | 393 passed, including temporal boundaries, cross-module reference cases, malformed inputs, corrupt/missing objects and injected filesystem failures. |
| `python -m pip check` | No broken requirements found. |
| `python -m pip wheel --no-deps --no-build-isolation --no-index --wheel-dir dist .` | Built `quant_test-0.1.0-py3-none-any.whl` without index access. |
| `python scripts/verify_hash_install.py dist/quant_test-0.1.0-py3-none-any.whl` | Passed: empty environment, invalid-hash rejection for an installed package, valid-hash reinstall. |
| Local Markdown destinations and heading fragments | All 113 resolved across the 25 tracked Markdown files plus this report; missing-path and missing-heading controls also rejected correctly. |
| `git diff --check` | Passed. |

Remote evidence was read through the connected GitHub tools:
[PR #10](https://github.com/matthiasdruhl/Quant-test/pull/10) is merged, and
[post-merge run 42712502514](https://github.com/matthiasdruhl/Quant-test/actions/runs/42712502514)
has successful [macOS job 129485437903](https://github.com/matthiasdruhl/Quant-test/actions/runs/42712502514/job/129485437903)
and [Ubuntu job 129485438323](https://github.com/matthiasdruhl/Quant-test/actions/runs/42712502514/job/129485438323).
Both job logs explicitly show checkout of `f9a49d8c8a8bca55bccb5c1a1a0678f31747d54c`
and 393 passing tests. This is CI evidence for the audited baseline, not a remote
run of these documentation edits.

## Assumptions and remaining limits

The current source and tests define implemented behavior; future requirements and
dated historical decisions are not implementation claims. No new independent
review or owner acceptance is asserted by this audit. Historical owner/reviewer
conversation records and the current ruleset configuration were not independently
reverified; their dated M0 evidence is retained as recorded. External links were
not exhaustively checked. A fresh third-party lock installation was not performed
locally; the existing environment check and offline wheel/hash check do not prove
its installation provenance. The verified baseline CI supplies separate clean
installation evidence on both supported platforms.

Provider integration, source authentication, full security master coverage,
validated dataset snapshots and all later-milestone functionality remain open in
the roadmap. No additional documentation mismatch was found within this scope.
