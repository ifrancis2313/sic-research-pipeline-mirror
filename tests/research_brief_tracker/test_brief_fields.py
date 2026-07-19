from datetime import date

from qepm.contracts import DimensionSpec, Direction, ExposureTarget
from qepm.research_brief_tracker import create_brief


def test_brief_carries_pod_capacity_deadline_and_factor_avoidances():
    target = ExposureTarget("T", Direction.BUY, 1_000, DimensionSpec(factor="quality"), "test")
    brief = create_brief(target)
    brief.pod_capacity = 3
    brief.target_pitch_date = date(2026, 8, 7)
    brief.factor_avoidances = ("AI crowding",)

    assert brief.pod_capacity == 3
    assert brief.target_pitch_date == date(2026, 8, 7)
    assert brief.factor_avoidances == ("AI crowding",)
