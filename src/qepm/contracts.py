"""Shared domain/range types that cross phase boundaries (ADR 0002).

Every dataclass here is a contract: a fixed shape one phase promises to
produce and the next phase is allowed to assume. Each module's own
``gate.py`` checks incoming data against these shapes before doing any
real work - this file only defines the shapes, it doesn't validate them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from enum import Enum

import pandas as pd


class PhaseGateError(ValueError):
    """Raised when data crossing a phase boundary fails its domain/range contract."""


class Direction(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Snapshot:
    """Phase 1 (Universe & Data Store) output: per-security panel + macro series."""

    as_of: date
    securities: pd.DataFrame  # indexed by "figi"; one column per security-level field
    macro: pd.DataFrame  # indexed by date; one column per market-wide series


@dataclass(frozen=True)
class FactorDefinition:
    """One entry in the Factor Registry: a named, scored signal over the universe."""

    name: str
    formula: Callable[[Snapshot], pd.Series]  # raw factor value per security
    weight: float
    description: str = ""
    required_fields: tuple[str, ...] = ()  # snapshot.securities columns this factor's formula reads
    required_macro_fields: tuple[str, ...] = ()  # snapshot.macro columns this factor's formula reads


@dataclass(frozen=True)
class FactorScoreMatrix:
    """Factor Registry output: one row per FIGI, one column per adopted factor."""

    as_of: date
    scores: pd.DataFrame  # indexed by "figi"; one column per factor name
    weights: dict[str, float] = field(default_factory=dict)  # factor name -> registry weight


@dataclass(frozen=True)
class Holdings:
    """Current portfolio positions, indexed by FIGI."""

    as_of: date
    positions: pd.DataFrame  # indexed by "figi"; column "dollar_value"


@dataclass(frozen=True)
class PortfolioPolicy:
    """V1's configurable binding limits for a same-snapshot Portfolio Fit Check."""

    portfolio_nav: float
    max_single_name_weight: float = 0.10
    min_median_daily_dollar_volume: float = 5_000_000.0
    max_trade_volume_fraction: float = 0.02
    beta_warning: float = 0.90
    beta_ceiling: float = 1.00
    beta_target_minimum: float = 0.75
    beta_target_maximum: float = 0.80
    beta_column: str = "market_beta_90d"
    beta_context_column: str = "market_beta_252d"
    liquidity_column: str = "median_daily_dollar_volume"
    factor_target_score: float = 55.0
    factor_watch_score: float = 45.0
    factor_priority_score: float = 35.0
    max_research_briefs: int = 5
    core_sleeve_minimum: float = 0.20
    core_sleeve_maximum: float = 0.25
    experimental_sleeve_minimum: float = 0.15
    experimental_sleeve_maximum: float = 0.20
    normal_cash_maximum: float = 0.05
    # Copied into each newly admitted trade as immutable approval evidence.
    # A later policy change governs new board approvals, never an existing one.
    material_price_move_fraction: float = 0.10
    russell_membership_column: str = "is_russell_1000"
    us_listing_column: str = "is_us_listed"
    instrument_type_column: str = "instrument_type"
    core_market_etf_column: str = "is_core_market_etf"
    price_history_column: str = "has_price_history"


@dataclass(frozen=True)
class GovernancePolicy:
    """Configurable ordinary Eboard rule; the V1 default records the agreed quorum."""

    ordinary_rule_id: str = "chair-plus-pm-or-lead-v1"
    chair: str = "Board Chair"
    ordinary_alternatives: tuple[str, ...] = ("PM", "Lead Analyst")
    exception_alternatives: tuple[str, ...] = ("PM", "Faculty Advisor", "Lead Analyst")


@dataclass(frozen=True)
class ResearchNeed:
    """A PM-reviewable, non-binding factor need for the weekly student queue."""

    factor: str
    direction: Direction
    current_score: float | None
    target_score: float
    priority: str  # priority | watch
    rationale: str


@dataclass(frozen=True)
class SizingRecommendation:
    """A quantitative size recommendation; never an autonomous approval or veto."""

    confidence: float
    recommended_weight: float
    maximum_weight: float
    requires_board_discussion: bool
    requires_above_five_percent_path: bool
    pitch_remains_eligible: bool = True


@dataclass(frozen=True)
class ScreenPredicate:
    """A machine-checkable screen condition - the structured counterpart to DimensionSpec.screen's display text."""

    field: str  # a snapshot.securities column
    op: str  # one of ">", "<", ">=", "<=", "=="
    threshold: float


@dataclass(frozen=True)
class DimensionSpec:
    """The sector/factor/screen combination an Exposure Target is scoped to."""

    sector: str | None = None
    factor: str | None = None
    screen: str | None = None  # human-readable predicate, e.g. "fcf_yield > 0.05" - for briefs/prompts
    screen_predicate: ScreenPredicate | None = None  # the same predicate, structured - for re-checking a pick


@dataclass(frozen=True)
class ExposureTarget:
    """Exposure Optimizer output: a dollar amount against a dimension, buy or sell."""

    id: str
    direction: Direction
    dollar_amount: float
    dimension: DimensionSpec
    rationale: str
    source_bucket: tuple[str, ...] = ()  # sell-side only: FIGIs responsible for overexposure
    sleeve: str | None = None  # core | active | experimental, assigned by PM when publishing a brief


@dataclass
class ResearchBrief:
    """Research Brief & Pitch Tracker: an Exposure Target packaged for analyst pods."""

    id: str
    target: ExposureTarget
    prompt: str
    assigned_pods: list[str] = field(default_factory=list)
    pitches: list[CompetingPitch] = field(default_factory=list)
    status: str = "open"  # open -> backtesting -> approved | rejected-returns-to-open
    claimed_on: date | None = None
    last_meaningful_update: date | None = None
    pod_capacity: int = 1
    target_pitch_date: date | None = None
    factor_avoidances: tuple[str, ...] = ()


@dataclass(frozen=True)
class CompetingPitch:
    """One pod's response to a Research Brief: a specific stock + thesis."""

    id: str
    brief_id: str
    pod: str
    figi: str
    thesis: str
    variant_view: str = ""
    dcf_sensitivity: str = ""
    cca_peers: str = ""
    catalysts_timeline: str = ""
    risks_disconfirming_evidence: str = ""
    fit_card_attached: bool = False


@dataclass(frozen=True)
class PitchReadiness:
    """Binary pitch qualification: Eboard, not a model, selects among ready pitches."""

    brief_id: str
    ready: tuple[CompetingPitch, ...]
    revise: dict[str, tuple[str, ...]]  # pitch id -> missing required artifacts


@dataclass(frozen=True)
class BacktestResult:
    """Backtest Gate output: pass/fail plus factor-fit and portfolio-impact detail."""

    pitch_id: str
    brief_id: str
    target_id: str
    passed: bool
    factor_fit: dict[str, float | None]
    estimated_impact: dict[str, float]
    notes: str = ""


@dataclass(frozen=True)
class TradeOrder:
    """An approved pick, formatted for handoff to a Trade Execution backend."""

    figi: str
    direction: Direction
    dollar_amount: float
    pitch_id: str
    brief_id: str
    target_id: str


@dataclass(frozen=True)
class PortfolioFitResult:
    """Same-snapshot pre-trade fit result, bound to its exact proposed order."""

    pitch_id: str
    brief_id: str
    target_id: str
    as_of: date
    passed: bool
    requires_exception: bool
    factor_fit: dict[str, float | None]
    estimated_impact: dict[str, float]
    hard_limit_violations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    notes: str = ""
    order: TradeOrder | None = None


@dataclass(frozen=True)
class CandidateFitCard:
    """Advisory context for student research; it never reserves capacity or rejects research."""

    figi: str
    research_permitted: bool
    fit: PortfolioFitResult
    available_name_room: float | None = None
    data_completeness: str = "complete"  # complete | factor-n/a | binding-data-missing
    crowding_status: str = "not-measured-v1"
    response_target_business_days: int = 2


@dataclass(frozen=True)
class ExecutionPriceLimit:
    """Pitch-owned valuation context and a side-aware limit for a proposed trade.

    ``limit_price`` is a maximum buy price or minimum sell price according to
    the associated TradeOrder's direction.  It is a review gate, never an
    automatic order or cancellation instruction.
    """

    reference_price: float
    limit_price: float
    rationale: str
    fair_value_per_share: float | None = None
    material_move_fraction: float | None = None


@dataclass(frozen=True)
class ExceptionRecord:
    """A human-approved, non-transferable override of named hard-limit failures.

    The record is deliberately bound to one order and one point-in-time fit.
    It cannot authorize a changed order, a later snapshot, a different set of
    violations, or any price/timing/warning review exception.
    """

    order: TradeOrder
    as_of: date
    hard_limit_violations: tuple[str, ...]
    rationale: str
    approvers: tuple[str, ...]


@dataclass(frozen=True)
class ProposedTrade:
    """An advisor-facing proposed change, pending execution rather than an order."""

    order: TradeOrder
    approved_on: date
    pitch_ready: bool
    approved_fit: PortfolioFitResult
    sizing: SizingRecommendation
    approval_nav: float
    decision: DecisionRecord | None = None
    price_limit: ExecutionPriceLimit | None = None
    exception: ExceptionRecord | None = None


@dataclass(frozen=True)
class ProposedTradeStatus:
    """Execution eligibility based on the age of an advisor-facing proposal."""

    eligible_for_execution: bool
    requires_retest: bool
    reason: str = ""


@dataclass(frozen=True)
class DecisionRecord:
    """Auditable Eboard decision with a configurable ordinary decision rule."""

    pitch_id: str
    approved: bool
    decided_on: date
    approvers: tuple[str, ...]
    ordinary_rule_id: str


@dataclass(frozen=True)
class FactorChangeProposal:
    """Evidence-gated request to change SIC's live factor methodology."""

    factor_name: str
    research_report_path: str
    independently_validated: bool
    approvals: tuple[str, ...]
    theory: str = ""
    exact_definition: str = ""
    point_in_time_treatment: str = ""
    limitations: str = ""
    expected_portfolio_effect: str = ""
    triggering_pitch_id: str | None = None
    proposed_definition: FactorDefinition | None = None


@dataclass(frozen=True)
class CampaignLeg:
    """One independently decidable pitch/target pair in a linked research campaign."""

    pitch: CompetingPitch
    brief: ResearchBrief


@dataclass(frozen=True)
class CampaignFitResult:
    """Binding fit results for the exact subset of campaign legs the Eboard approved."""

    approved_pitch_ids: tuple[str, ...]
    leg_results: tuple[PortfolioFitResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.leg_results)


@dataclass(frozen=True)
class HoldingOwnership:
    """Accountability record for an active or experimental holding thesis."""

    figi: str
    pod: str
    sleeve: str
    assigned_on: date
    inherited: bool = False
    legacy_review_complete: bool = False
    last_earnings_review: date | None = None
    last_quarterly_review: date | None = None


@dataclass(frozen=True)
class QueuePublication:
    """PM's auditable publication of the engine-proposed weekly research queue."""

    proposed_factors: tuple[str, ...]
    published_factors: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class BetaStatus:
    """Derived 90-day portfolio beta with a 252-day context check."""

    operational_beta: float | None
    context_beta: float | None
    status: str
    requires_exception_review: bool


@dataclass(frozen=True)
class StudentPulse:
    """Student-facing Friday work queue and non-sensitive portfolio context."""

    beta_status: str
    research_needs: tuple[ResearchNeed, ...]
    brief_statuses: dict[str, str]
    sleeves: dict[str, float]
    sleeve_statuses: dict[str, str]


@dataclass(frozen=True)
class EboardPulse:
    """Eboard Friday pulse, including position-level and advisor-queue detail."""

    beta_status: str
    research_needs: tuple[ResearchNeed, ...]
    brief_statuses: dict[str, str]
    sleeves: dict[str, float]
    sleeve_statuses: dict[str, str]
    holdings: pd.DataFrame
    proposed_trades: tuple[ProposedTrade, ...]


@dataclass(frozen=True)
class WeeklyCycleResult:
    """The two intentionally separated outputs from one Friday-close calculation."""

    student: StudentPulse
    eboard: EboardPulse


@dataclass(frozen=True)
class ExecutionResult:
    """Trade Execution output: traceable back through pitch -> brief -> target."""

    order: TradeOrder
    status: str
    backend: str
    confirmation_note: str = ""
