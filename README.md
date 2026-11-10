# Quant Test

A long-term, **research-first** quantitative equities platform. Initial focus: reproducible U.S. stock swing-trading research, not live trading.

> **Status:** M0 is complete on the [recorded evidence](docs/m0-evidence.md). M1 is active: temporal data contracts, in-memory historical catalogs, local raw payload/receipt storage with receipt-set quality counts, and receipt-linked observation metadata records are implemented. All M1 acceptance gates remain open. No trading strategy, backtesting engine, brokerage integration, or live execution is implemented. Nothing here establishes a profitable trading edge.

## Design priorities

1. **Point-in-time correctness** — no future information or survivorship bias.
2. **Reproducibility** — fixed data versions, code revisions, configurations, and seeds.
3. **Independent verification** — reference fixtures and adversarial tests, not just agent-written assertions.
4. **Separation of authority** — AI research code can never approve broker orders.
5. **Minimal complexity** — one modular Python package; no event bus or microservices until justified.

## Roadmap

0. Contracts, governance, and CI
1. Historical data and security master
2. Backtesting and accounting
3. Strategy baselines and statistical evaluation
4. Codex/Claude research agents
5. Macroeconomic and verified event intelligence
6. Insider, 13F, and public financial disclosure intelligence
7. Paper execution, reconciliation, and independent risk gates
8. Alternative data (satellite imagery is a later experiment)
9. Controlled deployment and portfolio monitoring

See [roadmap](docs/roadmap.md), [architecture](docs/architecture.md), [invariants](docs/invariants.md), and [AGENTS.md](AGENTS.md).

## Repository layout

```text
src/quant_test/
  core/          # Implemented timestamp availability checks
  data/          # Temporal catalogs, archive, receipts, linked metadata records
  research/      # Planned: features, experiment registry, evaluation
  backtest/      # Planned: simulation and accounting
  strategies/    # Planned: pure strategy implementations
  intelligence/  # Planned: macro, filings, news, alternative data
  portfolio/     # Planned: allocation and risk decisions
  execution/     # Planned: paper/live broker adapters; no execution path
tests/
  unit/          # Fast, deterministic tests
  integration/   # Reserved; no tests here yet
  contract/      # Reference cases and invariants
  fixtures/      # Small curated inputs
docs/decisions/  # Architecture decision records
```

Corporate actions, provider ingestion, curated datasets, and experiment/strategy
interfaces remain planned. Cross-module temporal/archive cases currently live in
`tests/contract/`; the [testing strategy](docs/testing-strategy.md) distinguishes
existing suites from future test layers. See the dated
[documentation audit](docs/documentation-audit.md) for review scope and evidence.

The [proposed first-source contract](docs/sources/databento-security-master.md)
assesses Databento Security Master as a possible listing-history candidate. Source
selection, usage rights and required temporal evidence remain unresolved; no
provider integration is approved or implemented.

## Local development

Use the exact Python baseline in [.python-version](.python-version), currently 3.11.17. Package metadata permits newer interpreters, but only the pinned baseline is covered by the reproducibility contract and CI. Start from a fresh virtual environment:

```bash
uv --version  # Required installer: uv 0.13.5 (see ADR 0003).
uv venv --python "$(cat .python-version)" --managed-python .venv
source .venv/bin/activate
uv pip install --python .venv/bin/python --require-hashes --only-binary=:all: --reinstall -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e ".[dev]"
python -m pip check
ruff check .
ruff format --check .
mypy src
pytest
```

CI runs on pushes to `main` and `codex/**` branches and on pull requests. It runs
these checks on Ubuntu and macOS, then builds/installs the wheel and checks
hash rejection before testing the installed distribution. Branch pushes can be
validated before a PR is opened. Successful M0 execution
is recorded in [M0 evidence](docs/m0-evidence.md); later implementation evidence
does not by itself close an M1 gate. See
[environment setup and lock updates](docs/environment.md).

## Implemented data primitives

The package implements timestamp availability, in-memory raw admission/quarantine
results, a historical revision selector, historical security listing lookup, and
point-in-time universe membership with a listing join. Admission alone does not
authenticate evidence or persist quarantine; [receipt storage](#raw-storage) adds
persistence separately. See
[ADR 0006](docs/decisions/0006-raw-availability-admission.md). Listing histories
preserve ended/delisted intervals, use separate effective and decision times, and
retain selected version provenance; see
[ADR 0007](docs/decisions/0007-historical-security-listings.md). Membership joins
preserve asserted stable IDs, select each source's eligible revisions independently,
and explicitly report unresolved mappings with provenance. They do not establish
provider coverage, universe completeness, provider integration, or validated
metadata persistence; see
[ADR 0008](docs/decisions/0008-point-in-time-universe-membership.md).

### Raw storage

The local raw payload archive persists exact bytes by SHA-256, verifies writes and
reads, and publishes without replacing existing objects. Consumers select a
historically eligible version before fetching its bytes; missing/corrupt content
fails explicitly. This requires a trusted local POSIX filesystem and provides no
crash durability or evaluable dataset snapshots; see
[ADR 0009](docs/decisions/0009-local-raw-payload-archive.md).

Frozen raw admission/quarantine receipts bind exact source/license assertions,
raw claims and payload checksum to a named admission policy. The archive stores
payload first and receipt last under a separate digest; reopen verifies both and
recomputes admission using a strict versioned codec that preserves precision and
DST gap/fold semantics. Receipt retention does not authenticate evidence, create
validated observation versions, or establish completed processing. The caller
retains receipt digests; validated metadata catalogs, quarantine workflows and
provider ingestion remain unimplemented. The existing archive's post-publication
cleanup failure and no-crash-durability limits apply; see
[ADR 0010](docs/decisions/0010-persisted-raw-admission-receipts.md).

Explicit raw receipt sets retain sorted distinct receipt digests and descriptive
admission/null/precision/status/reason counts. The archive verifies every selected
receipt/payload before publishing a canonical manifest/report and recomputes it on
reopen; corrupt or missing dependencies fail without partial results. Distinct
same-payload receipts count separately. Empty collections have zero counts; optional
source text and unknown event time may be absent on accepted receipts. This is
raw assertion reporting, without coverage, revision selection, validated promotion
or an evaluable dataset snapshot. See
[ADR 0011](docs/decisions/0011-raw-receipt-set-quality-report.md). All M1 gates remain open.

Receipt-linked observation records persist a separately supplied
`ObservationVersion` together with its exact accepted receipt reference. Publication
and reopen verify the receipt/payload and every shared identity, provenance and
timestamp field. Metadata timestamps normalize to canonical UTC; the receipt
retains original claims. This checks syntactic linkage, without authenticating
source assertions or promoting a receipt. Catalog inventories, provider ingestion
and evaluable snapshots remain future work; see
[ADR 0012](docs/decisions/0012-receipt-linked-observation-records.md).

The remaining contracts are documented in [data contracts](docs/data-contracts.md), [strategy targets](docs/strategy-contract.md), [research and holdout protocol](docs/research-protocol.md), [testing strategy](docs/testing-strategy.md), and [risk policy](docs/risk-policy.md). These documents distinguish implemented temporal validation and raw storage from future enforcement.

## Safety and scope

- Live trading is **not implemented** and must not be added without an explicit design and authorization review.
- Never commit API keys, brokerage credentials, or proprietary datasets.
- Data vendors' licenses and applicable securities regulations must be reviewed before collection or trading.
- Published disclosures are not contemporaneous holdings: historical features must use **when information was available**, not when an underlying trade occurred.

This is software research infrastructure, not investment advice.
