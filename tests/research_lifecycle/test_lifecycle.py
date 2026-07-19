from datetime import date, timedelta

from qepm.contracts import DimensionSpec, Direction, ExposureTarget, ResearchBrief
from qepm.research_lifecycle import advance_lifecycle, lifecycle_action


def test_brief_lifecycle_requests_a_two_week_check_and_four_week_resolution():
    start = date(2026, 7, 1)
    brief = ResearchBrief(
        "RB", ExposureTarget("T", Direction.BUY, 1_000, DimensionSpec(factor="quality"), "test"), "test",
        claimed_on=start,
    )

    assert lifecycle_action(brief, start + timedelta(days=14)) == "progress-check"
    assert lifecycle_action(brief, start + timedelta(days=28)) == "pitch-extend-narrow-or-release"
    assert lifecycle_action(brief, start + timedelta(days=7), meetings_without_update=2) == "release"


def test_lifecycle_releases_stalled_work_and_clears_pod_capacity():
    start = date(2026, 7, 1)
    brief = ResearchBrief("RB", ExposureTarget("T", Direction.BUY, 1_000, DimensionSpec(factor="quality"), "test"), "test", assigned_pods=["Pod A"], claimed_on=start)

    assert advance_lifecycle(brief, start + timedelta(days=7), meetings_without_update=2) == "release"
    assert brief.status == "released"
    assert brief.assigned_pods == []
