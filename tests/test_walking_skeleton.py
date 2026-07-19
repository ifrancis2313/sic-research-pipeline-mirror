"""End-to-end proof that all six modules wire together.

Fixture data only - no real factor definitions, no real risk constraints.
The point is the chain of interfaces and phase gates, not depth in any
one module. Each individual boundary's rejection behavior is covered in
that module's own test_gate.py; this test only exercises the happy path
all the way through.
"""

import subprocess
import sys
from pathlib import Path

from qepm.backtest_gate import evaluate_pitch
from qepm.contracts import CompetingPitch, Direction, TradeOrder
from qepm.exposure_optimizer import generate_exposure_targets
from qepm.research_brief_tracker import assign_pod, create_brief, score_pitches, submit_pitch
from qepm.trade_execution import execute_walking_skeleton_demo


def test_fixture_flows_through_every_phase_to_a_traceable_execution_result(
    snapshot, scores, holdings
):
    targets = generate_exposure_targets(snapshot, scores, holdings)
    assert len(targets) >= 1

    target = next(
        t
        for t in targets
        if t.direction is Direction.BUY and t.dimension.sector == "Energy" and t.dimension.factor == "momentum"
    )

    brief = create_brief(target)
    assign_pod(brief, "Pod A", claimed_on=snapshot.as_of)
    assert brief.status == "open"
    assert brief.assigned_pods == ["Pod A"]

    pitch = CompetingPitch(
        id="CP-1",
        brief_id=brief.id,
        pod="Pod A",
        figi="BBG-FIXTURE-007",  # Energy-sector fixture security, positive momentum
        thesis="Energy momentum play matching the brief's dimension.",
        variant_view="Market misses catalyst.",
        dcf_sensitivity="DCF with base, upside, and downside cases.",
        cca_peers="Peer set documented.",
        catalysts_timeline="Earnings catalyst in one quarter.",
        risks_disconfirming_evidence="Demand deterioration invalidates thesis.",
        fit_card_attached=True,
    )
    submit_pitch(brief, pitch, submitted_on=snapshot.as_of)

    readiness = score_pitches(brief)
    assert readiness.brief_id == brief.id
    assert readiness.ready == (pitch,)

    backtest_result = evaluate_pitch(pitch, target, brief, holdings, scores, snapshot, snapshot.as_of)
    assert backtest_result.passed is True
    assert backtest_result.pitch_id == pitch.id
    assert backtest_result.brief_id == brief.id
    assert backtest_result.target_id == target.id
    assert brief.status == "approved"

    order = TradeOrder(
        figi=pitch.figi,
        direction=target.direction,
        dollar_amount=target.dollar_amount,
        pitch_id=pitch.id,
        brief_id=brief.id,
        target_id=target.id,
    )
    execution_result = execute_walking_skeleton_demo(order, backtest_result)

    assert execution_result.status == "demo_complete"
    assert execution_result.backend == "WalkingSkeletonDemoExecutor"
    assert "DEMO ONLY" in execution_result.confirmation_note
    # traceable back through the whole pitch -> brief -> target chain
    assert execution_result.order.pitch_id == pitch.id
    assert execution_result.order.brief_id == brief.id
    assert execution_result.order.target_id == target.id


def test_walking_skeleton_script_is_runnable_from_the_project_root():
    project_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        [sys.executable, "scripts/run_walking_skeleton.py"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "6. Trade Execution" in result.stdout
    assert "demo_complete" in result.stdout
