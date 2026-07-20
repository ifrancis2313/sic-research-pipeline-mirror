# SIC QEPM Research Pipeline (public mirror)

This is a curated mirror of a factor-driven "optimal portfolio" pipeline built
for a student investment club's student-run equity fund — infrastructure
and methodology only, not a live trading system or a results post. It exists
to show the engineering and control-design work behind a quantemental
(quantitative + fundamental) portfolio process: a quantitative layer that
identifies portfolio needs and enforces risk limits, while students do the
fundamental research and the executive board makes the investment decision.

**What's deliberately excluded:** no live market-data feed, no individual
position sizes, trade blotter, or performance numbers, no vendor credentials,
and no internal planning/ticket history. The stated benchmark and long-run
core/active/experimental sleeve targets are policy decisions, not a live
holdings disclosure. Everything here runs against synthetic fixtures. See
`CONTEXT.md` for the full glossary and `docs/adr/` for the architecture
decisions behind it.

## What's here

| Folder | What's in it |
|---|---|
| `CONTEXT.md` | Glossary of terms used across the pipeline — start here if a word is unfamiliar. |
| `docs/adr/` | Architecture decisions: why the pipeline is shaped the way it is. |
| `src/qepm/` | The pipeline's code, one folder per module (see below). |
| `tests/` | Automated tests, mirroring `src/qepm/`'s folder structure one-for-one. |
| `scripts/` | A demo that walks synthetic fixture data through the whole pipeline so you can see it work end to end. |

## Core pipeline and V1 controls (`src/qepm/`)

The pipeline is six core modules, each its own folder:

1. `universe_data_store/` — resolves a point-in-time universe snapshot from
   a canonical FIGI-keyed identity layer. Holds the historical `DataStore`
   and its `adapters/` (one file per data source/format).
2. `factor_registry/` — scores that universe against adopted factors.
3. `exposure_optimizer/` — turns scores + holdings into dollar-denominated
   Exposure Targets (never stock-level instructions).
4. `research_brief_tracker/` — packages targets into research briefs and
   tracks competing analyst pitches against them.
5. `portfolio_fit/` — the public V1 interface for the same-snapshot
   Portfolio Fit Check run before an approved trade enters the advisor
   queue. It delegates to the retained `backtest_gate/` implementation,
   kept only for compatibility with the original walking-skeleton naming.
6. `trade_execution/` — creates the policy-required advisor handoff for an
   approved trade.

Pitch readiness is a structural completeness check: it verifies that the
required research artifacts are attached, while the executive board
evaluates the substance of the thesis, valuation, and risks.

The optimizer produces active-sleeve research needs by default. When
publishing a brief, the portfolio manager may explicitly select `core`,
`active`, or `experimental` through `create_brief(target, sleeve=...)`; that
recorded sleeve is then enforced by the Portfolio Fit Check. This keeps
core-market transitions and experimental research as human policy decisions
rather than inferences from an active-universe score.

Supporting V1 workflow modules include `campaigns/`, `candidate_precheck/`,
`position_sizing/`, `beta_monitoring/`, `portfolio_pulse/`, `research_queue/`,
`queue_publication/`, `research_lifecycle/`, `holding_ownership/`,
`governance/`, `factor_governance/`, `advisor_queue/`, `advisor_workbook/`,
`sleeves/`, and `weekly_cycle/`. Shared `portfolio_state.py` validation keeps
policy, holdings, and trade-order checks consistent across those controls.

`holding_ownership/`'s pod-ownership, legacy-review, and quarterly-refresh
rules are implemented and tested in isolation, but no `weekly_cycle` or
`advisor_workbook` caller creates or enforces an ownership record yet —
tracking a holding's owner remains a manual process until that orchestration
is built.

`trade_execution.execute_live_proposed_trade()` is the only supported
advisor-handoff entry point. It requires the full V1 live-snapshot
readiness contract, a configured advisor workbook, and the workbook
revision just read by the operator before it can format a handoff. It
atomically records one `prepared_for_advisor` entry in the workbook's
durable Handoff Ledger and refuses an identical approved proposal a second
time. This is a manual-handoff control, not broker execution or a
fill/cancellation ledger. `execute_proposed_trade()` is a lower-level
deterministic seam used by tests and fixture exercises, not a live-run
claim. The legacy walking-skeleton path is named
`execute_walking_skeleton_demo()` and uses a simulated demo backend, never
the advisor formatter.

Policy requires all real orders to go through a faculty advisor. Direct
broker execution and advisor automation are not supported architecture or a
roadmap item; a policy change would require a separate control design.

The advisor formatter is a private implementation detail rather than a
public raw-`TradeOrder` API. This reduces accidental bypasses, but it is not
a security boundary in Python; repository permissions and the human
execution workflow remain the actual access controls.

Each module also has a `gate.py` — a checkpoint that rejects bad data
coming from the previous module rather than letting it silently break
something downstream (see ADR 0002 in `docs/adr/`).

`src/qepm/contracts.py` defines the shapes of data that pass between
modules (Snapshot, ExposureTarget, ResearchBrief, etc.) — the shared
vocabulary the modules use to talk to each other. `src/qepm/scoring.py` is
a small shared utility for factor-score composition.

`advisor_workbook.write_advisor_workbook()` refreshes one configured
advisor-facing `.xlsx` file with current positions and approved, unexecuted
trades. It preserves a manually maintained Execution History sheet across
refreshes. Each pending trade carries its pitch-owned execution price limit
and is visibly flagged for human review when price (including an
approval-time material-move threshold), fit freshness, or its 30-calendar-day
approval-anniversary retest rule requires it. These are pre-execution review
controls, not stop-losses or automatic cancellation instructions. Positions
intentionally show FIGI, current price, and dollar value only: a
security-panel `shares` field is not assumed to be actual shares held.
Refreshing an existing workbook requires its current
`advisor_workbook.workbook_revision()` value, so a human edit causes an
explicit conflict instead of a silent overwrite; the operator must reload
and rerun the refresh.

The same workbook also preserves its Handoff Ledger across queue refreshes.
Before a live handoff, `workbook_revision(path)` is read and that exact
value passed to `execute_live_proposed_trade(..., workbook_path=path,
expected_workbook_revision=revision)`. A changed workbook fails closed
rather than overwriting a human edit; a ledger entry records only that the
immutable, approved proposal was prepared for the advisor, including who
prepared it. Confirmed fills remain manual entries in Execution History.

`advisor_queue.reconcile_pending_trade_fits()` recomputes every pending
trade's current, canonical Portfolio Fit result against a fresh same-as_of
snapshot, purely (no queue/approval/brief-status mutation) and fail-closed
on any provenance mismatch. It's implemented and directly tested, but no
`weekly_cycle` or `advisor_workbook` caller invokes it yet before a workbook
refresh — the recurring "did an approved trade's warnings change since
approval" check it exists to support isn't wired into an actual weekly
operating cycle yet. `advisor_queue.validate_current_fit_for_order()` is a
related, currently-unused primitive superseded in practice by an equivalent
inline check inside `advisor_workbook.review_pending_trade()`.

## Methodology highlights

- **Point-in-time discipline everywhere.** Every phase boundary runs a
  domain/range contract check and a leakage check: any derived/rolling
  field carries a companion availability-date column, and a gate rejects a
  computation that could not have been known as of the decision date. This
  is the core defense against look-ahead bias, applied at every phase
  boundary, not just the data-ingestion layer.
- **Advisory vs. binding, kept structurally separate.** Factor scores,
  candidate prechecks, and pitch confidence are always advisory — they
  inform research and sizing but never veto a pitch or auto-select a trade.
  Liquidity, concentration, beta, and universe-eligibility checks are
  binding and fail closed on missing data.
- **No fabricated or imputed data.** A missing factor score is surfaced as
  `N/A`, never filled in with a guess; missing binding risk data blocks a
  trade rather than being silently defaulted.
- **Four-person evidence gate for methodology changes** (see ADR 0005): a
  factor definition/weight/threshold change requires a substantive research
  report and independent validation from all four named governance roles —
  it cannot be justified by an active pitch alone.
- **Mutation testing on the binding-limit modules**, not just coverage:
  `mutmut`, scoped to `backtest_gate/`, `position_sizing/`, `governance/`,
  `exposure_optimizer/`, `scoring.py`, and `factor_registry/v1.py` (see
  `pyproject.toml`'s `[tool.mutmut]`), to distinguish tests that actually
  verify these limits from ones that pass regardless of whether the logic
  they claim to check is right. Two triage passes found and closed real
  gaps, not just boundary conditions: none of the four hard-limit boundary
  checks (liquidity floor, participation cap, single-name cap, beta
  ceiling) had a test at the exact threshold value; an already-breached
  position could get measurably worse without being flagged as a hard
  violation; a NaN (not just missing/`False`) price-history value could
  silently pass the fit check; three separate `continue`-inside-a-loop
  statements had no test proving a skipped item doesn't silently drop
  every later item too (verified as a real, reproducible bug class, not
  hypothetical — mutating any one of them to `break` passed the full
  suite before a targeted test was added); `PortfolioFitResult.order` —
  the field the admission-attestation check binds a trade to — was never
  verified as actually populated by `evaluate_portfolio_fit()` itself,
  only by hand-built test fixtures; and the V1 factor registry's
  `required_fields` tuples (what the Data→Factor gate actually enforces)
  had zero direct test coverage. Current state: **1082/1271 mutants
  killed (~85%)**, not run to zero — remaining survivors are heavily
  weighted toward message/description-string mutations (verified by
  sampling, not assumed), and a full one-by-one triage of every remaining
  survivor has not been completed.
- **Property-based testing** (Hypothesis) for the pure-math functions
  (factor blending, percentile ranking, position-sizing bands), alongside
  example-based unit tests. Found one genuine floating-point edge case
  (`combined_factor_score` losing precision at denormalized-float weight
  magnitudes no real factor registry would ever use) and pinned it with a
  documented, deliberately-bounded input domain rather than silently
  ignoring it.
- **A statically-enforced architecture boundary**: a test walks the actual
  AST of every module in `src/qepm/` (outside `trade_execution/`) and fails
  if the private advisor-executor classes are referenced anywhere else, so
  "the advisor formatter is private" is a checked invariant, not just a
  naming convention backed by a docstring.
- **CI** (GitHub Actions): ruff + mypy + pytest + `pip-audit` dependency
  scanning on every push, against a pinned lockfile.

## Running it

```
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock
PYTHONPATH=src pytest -q
ruff check .
mypy src
PYTHONPATH=src python scripts/run_walking_skeleton.py   # watch fixture data flow through every module
```

No market data or credentials required — everything here runs against
synthetic fixtures. A handful of adapter-level tests skip automatically when
their (deliberately untracked) source-backed fixtures aren't present in this
public-safe clone.

`hypothesis` runs as part of the normal test suite above (no separate step).
`mutmut` is a manual, periodically-run audit tool, not a CI gate — reproduce
it locally with `pip install mutmut && PYTHONPATH=src mutmut run` (scope is
set in `pyproject.toml`'s `[tool.mutmut]`), then `mutmut results` to list
survivors.

## Status

This is an active, local-first V1 implementation: an approved
Value/Quality/Momentum factor methodology, advisory prechecks, ready/revise
pitch qualification, a binding Portfolio Fit Check, confidence-aware sizing,
a sleeve-aware weekly pulse, and a dated advisor queue are all implemented
and tested against fixtures. Live market-data wiring and a real brokerage/
advisor connection are explicitly out of scope for this repository — the
production cutover path requires licensed data access and a separate,
human-reviewed go-live process that isn't part of this codebase.

## License

MIT — see `LICENSE`.
