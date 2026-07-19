#!/usr/bin/env python3
"""Runnable demo: walks one fixture Exposure Target through all six QEPM modules.

Not real data, not a real factor, not a real trade - this exists so the
pipeline's shape can be seen end to end before any
module gets real depth. Run it with:

    .venv/bin/python scripts/run_walking_skeleton.py
"""

from __future__ import annotations

from datetime import date

from qepm.backtest_gate import evaluate_pitch
from qepm.contracts import CompetingPitch, Direction, TradeOrder
from qepm.exposure_optimizer import generate_exposure_targets
from qepm.factor_registry import FactorRegistry, score_universe
from qepm.factor_registry.stub_factors import STUB_MOMENTUM
from qepm.research_brief_tracker import assign_pod, create_brief, score_pitches, submit_pitch
from qepm.trade_execution import execute_walking_skeleton_demo
from qepm.universe_data_store import get_universe_snapshot
from qepm.universe_data_store.fixtures import fixture_holdings


def main() -> None:
    as_of = date.today()

    print(f"1. Universe & Data Store: fixture snapshot as of {as_of}")
    snapshot = get_universe_snapshot(as_of)
    holdings = fixture_holdings(as_of)
    print(f"   {len(snapshot.securities)} fixture securities, {len(holdings.positions)} current holdings\n")

    print("2. Factor Registry: scoring against one stub factor (momentum)")
    registry = FactorRegistry()
    registry.register(STUB_MOMENTUM)
    scores = score_universe(snapshot, registry)
    print(scores.scores.to_string(), "\n")

    print("3. Exposure Optimizer: generating exposure targets")
    targets = generate_exposure_targets(snapshot, scores, holdings)
    for t in targets:
        print(f"   [{t.direction.value.upper()}] {t.id}: ${t.dollar_amount:,.0f} - {t.rationale}")
    print()

    target = next(
        t
        for t in targets
        if t.direction is Direction.BUY and t.dimension.sector == "Energy" and t.dimension.factor == "momentum"
    )
    print(f"4. Research Brief & Pitch Tracker: packaging {target.id}")
    brief = create_brief(target)
    assign_pod(brief, "Pod A", claimed_on=as_of)
    print(f"   Brief prompt: {brief.prompt}")

    pitch = CompetingPitch(
        id="CP-DEMO-1",
        brief_id=brief.id,
        pod="Pod A",
        figi="BBG-FIXTURE-007",
        thesis="Energy-sector pick carrying positive momentum, matching the brief's dimension.",
        variant_view="Catalyst is underappreciated.",
        dcf_sensitivity="Base, upside, and downside cases prepared.",
        cca_peers="Comparable energy peers documented.",
        catalysts_timeline="One-quarter catalyst timeline.",
        risks_disconfirming_evidence="Demand weakness invalidates the thesis.",
        fit_card_attached=True,
    )
    submit_pitch(brief, pitch, submitted_on=as_of)
    readiness = score_pitches(brief)
    print(f"   Pitch submitted: {pitch.figi} ({pitch.thesis})")
    print(f"   Ready pitches: {[ready_pitch.id for ready_pitch in readiness.ready]}")
    print()

    print("5. Backtest Gate: checking the winning pitch's factor loadings")
    backtest_result = evaluate_pitch(pitch, target, brief, holdings, scores, snapshot, as_of)
    print(f"   Passed: {backtest_result.passed}")
    print(f"   Factor fit: {backtest_result.factor_fit}")
    print(f"   Estimated impact: {backtest_result.estimated_impact}")
    print(f"   Brief status: {brief.status}\n")

    print("6. Trade Execution: simulating the traceable demo order")
    order = TradeOrder(
        figi=pitch.figi,
        direction=target.direction,
        dollar_amount=target.dollar_amount,
        pitch_id=pitch.id,
        brief_id=brief.id,
        target_id=target.id,
    )
    execution_result = execute_walking_skeleton_demo(order, backtest_result)
    print(f"   {execution_result.confirmation_note}")
    print(f"   Status: {execution_result.status} (backend: {execution_result.backend})")


if __name__ == "__main__":
    main()
