# QEPM Research Pipeline — Architecture Context

The Student Investment Committee (SIC)'s QEPM (quantitative equity portfolio management) pipeline: builds and maintains a factor-driven "optimal portfolio" for SIC's $100K student-run equity fund, replacing its current passive Russell/S&P index-ETF holdings. The pipeline is organized into four sequential **Phases**, each with its own validated input/output contract (see the Domain/range contract and Phase gate entries below).

## Language

**Universe**:
The fixed factor-comparison and core/active trade universe: Russell 1000 constituents. It is locked at pipeline start, not an analyst-pitchable parameter (unlike a **Factor**). U.S.-listed stocks and ETFs outside it may be eligible only for the **Experimental sleeve**, where they are clearly labeled experimental and remain subject to the same hard risk envelope.

**Policy benchmark**:
The stable market yardstick used to measure SIC portfolio performance and market beta: the Russell 1000, with IWB as its daily implementation proxy. It is not the same thing as the current holdings mix or the amount held in the **Core market sleeve**.

**Weekly portfolio snapshot**:
The point-in-time input to SIC's Friday portfolio pulse, based on Friday closing prices and volumes plus all SEC filings available by that run. Fundamental observations carry forward from the latest valid filing until updated. It is a weekly control snapshot, not an intraday or real-time feed.

**Portfolio pulse**:
The Friday report generated from the **Weekly portfolio snapshot**. Its student-facing view contains sleeve mix, beta/factor traffic lights, research briefs, active/expiring work, and portfolio needs/constraints. Its executive-board view additionally contains individual position sizes, exact factor exposures, proposed trade quantities, and the **Proposed-trades queue**.

**Market beta**:
The portfolio's sensitivity to the **Policy benchmark**, treated as a portfolio-risk control rather than a stock-selection score. SIC targets 0.75–0.80 beta, warns at 0.90, and caps it at 1.00. It monitors a 90-trading-day rolling beta for current conditions and shows a 252-trading-day beta as longer-term context; a sustained breach or agreement between the two windows triggers the exception process. Beta describes the market-driven component of returns, not the portfolio's total volatility or its ability to outperform the benchmark.

**Core market sleeve**:
The long-run 20–25% allocation to broad market exposure, implemented through IWB as SIC transitions away from its inherited IWB/SPY mix. The sleeve is governed by its allocation band rather than the single-company position cap.

**Active sleeve**:
The default sleeve for optimizer-generated research needs: individual Russell 1000 names selected through the normal research-brief/competing-pitch process. Every `ExposureTarget` the optimizer produces is stamped `active` unless a PM explicitly overrides it at brief-publish time (see **Experimental sleeve**).

**Experimental sleeve**:
The long-run 15–20% allocation for U.S.-listed stocks/ETFs outside the Russell 1000 **Universe**, or otherwise outside the active sleeve's normal eligibility. A PM selects it explicitly via `create_brief(target, sleeve="experimental")`; it remains subject to the same beta, liquidity, sizing, and concentration controls as any other sleeve — being experimental changes eligibility, not risk limits.

**Cash posture**:
SIC has no strategic cash sleeve: 0–5% cash is normal operating capacity for dividends, timing, and pending execution. Cash above 5% is flagged in the portfolio pulse as a funding opportunity, not an automatic buy order. The board may deliberately carry more cash when it chooses; the system records and surfaces that decision without forcing deployment.

**Canonical identifier**:
FIGI (Financial Instrument Global Identifier) — the vendor-neutral ID Phase 1 mints/crosswalks to, since QEPM draws data from both Bloomberg and FactSet (student licenses) and needs an ID scheme owned by neither.
_Avoid_: Bloomberg ticker or FactSet entity ID as the primary key — vendor-specific, crosswalked into FIGI instead.

**Factor**:
A named, scored signal over the **Universe** (e.g. value, momentum, quality) that feeds into the portfolio optimizer as one input among several. An analyst "pitch" proposes either a new **Factor** or a change to an existing one's definition/weight.
_Avoid_: using "factor" loosely for universe/screen/constraint changes — those are separate, non-pitchable configuration, not factors.

**Factor methodology**:
SIC's shared language for describing what the active sleeve seeks or lacks — for example, "seek quality without increasing AI/growth crowding." V1 generally seeks positive Quality, Value, and Momentum tilts with equal default priority; treats Size as neutral monitoring rather than a small-cap preference; and governs market sensitivity through **Market beta** separately. Quality and Value are measured relative to sector peers; Momentum is measured across the full **Universe**; Size remains a whole-universe monitor. Quality, Value, and Momentum use advisory 0–100 percentile bands: 55+ is target, below 45 is a watch, and below 35 is a priority research gap. Factors guide research briefs and portfolio exposure targets; they do not replace student name selection or the hard risk envelope.

**Residual PCA**:
A future crowding diagnostic, not a V1 sizing method. Once SIC has sufficient clean factor-model history, it may be run on factor-model residuals in shadow mode to flag crowding for a future cycle. It never automatically sets V1 position sizes or replaces named factor and beta controls.

**Factor-change gate**:
The sole approval path for adding, removing, or materially changing a live factor definition, formula, direction, or threshold. A proposer submits a substantive research report and thesis; the change must be independently validated and approved by the PM, Board Chair, Lead Analyst, and Faculty Advisor before it affects the live Factor methodology or research queue. No active pitch may drive an ad hoc factor change.

**Exposure target**:
Phase 3's raw output: a dollar amount plus whatever combination of sector/factor/screen dimensions justifies it (e.g. "$5K into Sector X" or "$5K into Sector X passing an FCF screen"), in either direction — buy-side (add exposure) or sell-side (an overexposed factor/sector traced to a specific bucket of current holdings). Not stock-level; see [ADR 0001](docs/adr/0001-exposure-optimization-plus-human-stock-selection.md).

**Research brief**:
The human-facing packaging of an **Exposure target** into an assignable project for an analyst — "find/pitch a stock that fits this" (buy-side) or "pick which of these current holdings to trim" (sell-side). The same brief may be issued to multiple analysts as **Competing pitches**. The initial standard brief declares: portfolio need and direction; factor objective and avoidances; why it matters now; pod capacity and research deadline; applicable constraints (such as liquidity, position room, and existing overlap); and required pitch outputs (thesis, DCF, CCA, catalysts, and risks). This is a living template, not a frozen rubric.

**Research brief queue**:
The rolling, PM-owned list of up to five available, in-progress, ready-to-pitch, and expired **Research briefs** published with the weekly portfolio pulse. The engine may propose an order from factor gaps and portfolio constraints, but the PM has final publication control: reorder, suppress, or add a brief before students see it. Each brief has a pod capacity, and multiple pods may deliberately work a high-priority brief as **Competing pitches**. An in-progress brief remains visible until pitched, extended, narrowed, or released; an untouched brief may be suspended when portfolio priorities change.

**Research campaign**:
A high-priority portfolio need that requires a linked package of two or more **Research briefs** — for example, a quality buy plus two trims to reduce an unwanted concentration. The PM sets capacity per brief. Individual pitches/trade legs may be approved at a smaller size or rejected independently; the final risk check evaluates the actual approved subset together, not each linked trade in isolation.

**Research window**:
The time a pod has to advance a claimed **Research brief**: a progress check after two weeks, then pitch, explicit extension, narrowing, or release by weeks three to four. Two meetings without a meaningful update releases the brief back to the queue.

**Liquidity guardrail**:
A binding pre-trade control. A stock or ETF needs at least $5 million of median daily dollar volume across the preceding 30 trading days, and the proposed net buy or sell cannot exceed 2% of that median volume. Any exception follows the portfolio exception process.

**Position-size recommendation**:
The engine's portfolio-context recommendation for a qualifying pitch, subject to the hard risk envelope and PM approval. V1 uses 3% as the normal initial position but may recommend 1–5% based on portfolio need and available risk capacity. A position above 5% requires all of: an engine recommendation, a new student pitch/reassessment, a fresh binding risk check, and PM approval. No individual name may exceed 10% of the portfolio.

**Pitch confidence**:
The V1 meta-labeling output used by the **Position-size recommendation**. It is a quantitative input to sizing, not a substitute for the student thesis or executive-board decision. Initial bands are high at 0.70 or above (full 1–5% initial recommendation range), medium from 0.45 through 0.69 (maximum 3%), and low below 0.45 (maximum 1% plus explicit board discussion). It is not an automatic veto: the board may decline any pitch after considering the complete diagnostics. The cutoffs are configurable and must be revalidated as the model develops.

**Exception quorum**:
The minimum valid approval for overriding a binding portfolio limit: Board Chair plus one of the PM, Faculty Advisor, or Lead Analyst. The usual practice is for the PM and Board Chair to involve Faculty Advisor in material exceptions, with the Lead Analyst adding analysis; however, Board Chair plus the Lead Analyst is a valid quorum when neither is involved.

**Hard-limit exception record**:
The human-entered audit record for one approved override. It names the exact
order, the exact Portfolio Fit Check snapshot date, the exact non-empty set of
hard-limit violations, the rationale entered by the portfolio manager, and the people who
approved it. It is invalid if the order, snapshot, or violations change. It
does not bypass the execution price limit, material-price review, a new
warning, or the 30-day retest; those always require their normal review path.

**Proposed-trades queue**:
The running advisor-facing spreadsheet of executive-board-approved trade changes awaiting execution. A trade enters it only after its pitch, sizing recommendation, and binding risk check have been run and approved; its approval date is recorded. It gives Faculty Advisor a continuously current view of intended position changes. Faculty Advisor and the PM set its review and execution cadence separately; the system does not force a monthly or other fixed calendar. An unexecuted trade older than 30 calendar days must be retested before Faculty Advisor executes it.

**Execution price limit**:
The pitch-owned, DCF/value-grounded maximum buy price or minimum sell price,
with the authors' rationale and the approval-snapshot reference price. It is
captured with every advisor-queue proposal. The weekly system check reruns
the current Portfolio Fit Check but escalates only an actual exception: a
current price outside the side-aware limit, a material move of 10% or more
from the reference price, a failed/mismatched current fit, or the 30-day retest
deadline. None automatically cancels, re-approves, or executes a trade.
The 10% threshold is a configurable PortfolioPolicy value, copied into each
approved proposal as immutable evidence; changing policy affects later board
approvals, not trades already pending execution.

**Advisor workbook**:
The one durable spreadsheet refreshed at a configured path for Faculty Advisor and
the PM. Each run replaces the current Positions and Pending Trades views,
but preserves the human-confirmed Execution History and structured Exception
Log sheets. It is a review
and handoff surface, not a broker or automated order-management system.

**Rebalance recommendation**:
An engine recommendation to trim or eventually exit an existing holding because it no longer fits the portfolio's factor, beta, liquidity, concentration, position-size, or sleeve needs. It is not a mechanical stop-loss or a response to price alone. SIC is a buy-and-hold portfolio: price is reported for context but creates no automatic review or trade trigger, and a recommended trim or exit still follows the same student research, executive-board decision, and binding risk process as a purchase.

**Holding owner**:
The pod accountable for maintaining a holding's thesis after it enters the active or experimental sleeve. The original pitching pod owns it until an explicit handoff. Every inherited holding receives a one-time legacy-review brief before assignment. Owners refresh the thesis after earnings and at least quarterly; a review alone does not compel a trade.

**Competing pitch**:
One analyst's response to a **Research brief** (a specific stock + supporting research, e.g. a DCF). Multiple analysts may pitch against the same brief. The system gives each an advisory fit card and applies the binding risk envelope, while the shared fundamental rubric classifies the pitch as ready or revise; it does not statistically rank pitches into a winner. Students research and argue the case, and the executive board makes the final investment decision after considering thesis, DCF, CCA, catalysts, risks, and portfolio fit.

**Pitch rubric**:
The binary ready/revise standard for a **Competing pitch**. A ready pitch includes a clear thesis and variant view; transparent DCF assumptions and sensitivity; relevant CCA with a defensible peer set; catalysts and timeline; risks and disconfirming evidence; and its precheck/portfolio-fit card. It assures a complete fundamental case but does not select a winner.

**Candidate precheck**:
An advisory fit card the PM returns within a two-business-day target after a student submits a prospective ticker. It identifies core/active versus experimental eligibility, factor effect, beta effect, liquidity result, available position/sleeve room, and crowding concerns. It neither rejects the student's research nor reserves portfolio capacity; the binding check reruns when a proposed trade is approved.

**Data completeness**:
The visible status of data required to assess a pitch. SIC never imputes or fabricates a factor value. Missing binding risk data—identity, price history, liquidity, or position data—prevents a trade unless formally excepted. Missing or non-comparable factor data is shown as `N/A`; the pitch may still be approved, but the gap is weighed explicitly in the fundamental and executive-board evaluation.

**Candidate shortlist**:
A possible future enhancement, not yet built: Phase 3 auto-generating a shortlist (e.g. ~5 tickers) matching a **Research brief**'s screen, to help the PM tighten the brief before assigning it. Deliberately left as an open extension point, flagged and deferred rather than designed speculatively.

**Ownership model**:
Single-writer across the *entire* QEPM pipeline (Phases 1-4), not just Phase 1 — the PM and **Lead analyst** are the only two people who touch the live pipeline code. Analysts never get their own running Phase 2-4 instance. Analysts contribute only via pitches — a **Factor** pitch (proposing new/changed model inputs) or a **Competing pitch** (proposing a stock against a **Research brief**) — whose form varies by analyst (quant-backed sandboxed research vs. fundamental research). The executive board makes the final investment decision; implementation remains PM-controlled and no pitching analyst directly operates the live pipeline.

**Lead analyst**:
The PM's co-gatekeeper for the centralized pipeline — see **Ownership model**.

**Governance**:
Students own research and present their recommendations; the executive board makes final investment decisions after the system applies its guardrails. An ordinary trade approval requires Board Chair plus either the PM or Lead Analyst; Faculty Advisor is informed through the advisor queue rather than made a voting dependency. The PM controls live execution. **Exception quorum** is separate and already defined.

**Pod**:
One trained analyst mentoring several regular (untrained) students, working together on assigned **Research briefs** — the scaling mechanism for the training program beyond just the PM and **Lead analyst** teaching everyone directly. Multiple pods may work the same brief as **Competing pitches**; overlap is expected and fine, not a fallback case to avoid.

**Optimizer cadence**:
Phase 3 runs weekly-to-biweekly (targeted: Monday mornings), plus ad hoc manual runs whenever new data comes in. Not fully automated/continuous — the PM triggers runs manually rather than the pipeline self-scheduling.

**Domain/range contract**:
The fixed, versioned input type (domain) and output type (range) each phase commits to — applied explicitly at *every* phase boundary in QEPM, not just Phase 1's. A phase's internals can change freely; its contract can't change without a version bump.

**Phase gate**:
The validation step each phase runs on its upstream input before processing it, checking exact conformance to that boundary's **Domain/range contract** — malformed or out-of-range data is rejected/flagged there rather than allowed to silently corrupt downstream phases. Includes a **Leakage check** where the phase involves compressing/summarizing raw history.
_Avoid_: "lock and dam" (the PM's original phrasing) as the term going forward — kept here as a note since it's where the concept came from.

**Leakage check**:
Part of a **Phase gate**: confirms a compressed/summarized field (e.g. a rolling factor score) only uses information actually available as of that point in time, and that **Universe** membership is applied point-in-time rather than today's constituent list projected backward. Catches lookahead/survivorship bias that would make a backtest look better than live trading would.

**Per-security panel**:
Phase 1's primary output shape: a table keyed by **Canonical identifier** (FIGI) × date, one column per field. Holds anything crosswalkable to a specific security (price history, fundamentals, ESG scores).

**Macro series**:
Phase 1's secondary output shape: a date-keyed (no security key) table of market-wide series — e.g. Fed funds rate, Fama-French factor returns, VIX family. Exists alongside the **Per-security panel** rather than being broadcast into it; Phase 2 may reference either or both when scoring a **Factor**.

**Adapter**:
A source- and format-specific mapping (e.g. a single-ticker Excel export, a bulk multi-ticker parquet file) into Phase 1's **Domain/range contract** (the **Per-security panel** / **Macro series** pair). Adding a new data source, vendor, or file format is always a new adapter, never a change to Phase 2+.

**Trade execution**:
SIC policy requires every real trade to be routed through its faculty advisor.
The pipeline creates a governed, ledgered advisor handoff; it is not and does
not plan to become a direct-broker or automated order-management system.
This policy boundary is separate from SIC's internal investment governance.
Any future change would require an explicit SIC policy change and a separately
designed control framework.

## Relationships

- **Phase 1** (Bloomberg/FactSet and other **Adapter**-ingested data, **Universe** = Russell 1000, keyed by **Canonical identifier**; output is a **Per-security panel** + **Macro series** pair) feeds **Phase 2** (**Factor** pitches, adopted into the multifactor model) feeds **Phase 3** (optimizer producing **Exposure targets**).
- Every phase-to-phase handoff passes through a **Phase gate** validating the **Domain/range contract** — not just Phase 1 into Phase 2.
- An **Exposure target** is packaged into a **Research brief**, which may draw multiple **Competing pitches**; ready pitches receive the binding **Portfolio Fit Check** and are decided by the Eboard before PM-controlled implementation. This human research loop is *not* strict one-way pipeline composition — see [ADR 0001](docs/adr/0001-exposure-optimization-plus-human-stock-selection.md).

## Example dialogue

> **Dev:** "Phase 3 flagged us $5K underexposed to Industrials on quality. What happens next?"
> **PM:** "That's an **Exposure target** — I turn it into a **Research brief** and hand it to a couple of **Pods**. Each pod comes back with a **Competing pitch** — a specific stock plus their DCF and CCA. The rubric marks pitches ready or revise; it does not rank a winner. The Eboard selects among the ready cases."
> **Dev:** "What protects the portfolio once the Eboard picks a case?"
> **PM:** "The same-snapshot **Portfolio Fit Check** applies liquidity, price-history, beta, name-cap, and sleeve-eligibility controls. Confidence informs a sizing recommendation, never a veto. The Eboard makes the decision; the controls make the risk visible and stop a trade that breaches a hard limit."

## Flagged ambiguities

- Earlier drafts of this glossary used "Block 1-4" for the four-stage shape. Resolved: renamed to "Phase 1-4" throughout, matching how the pipeline's own operator refers to them in conversation.
- V1 factor definitions and operating limits are implemented as configurable `PortfolioPolicy` defaults. They are not permanent: a factor-methodology change requires a recorded research report, independent validation, and approval by the PM, Board Chair, Lead Analyst, and Faculty Advisor (see ADR 0005).
