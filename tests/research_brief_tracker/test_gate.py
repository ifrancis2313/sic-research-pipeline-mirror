from dataclasses import replace

import pytest

from qepm.contracts import DimensionSpec, Direction, ExposureTarget, PhaseGateError
from qepm.research_brief_tracker import create_brief

BASE_TARGET = ExposureTarget(
    id="ET-BUY-ENERGY",
    direction=Direction.BUY,
    dollar_amount=21_882.35,
    dimension=DimensionSpec(sector="Energy", factor="momentum"),
    rationale="Energy is underexposed.",
)


def test_rejects_target_with_non_positive_dollar_amount():
    bad_target = replace(BASE_TARGET, dollar_amount=0.0)

    with pytest.raises(PhaseGateError, match="non-positive"):
        create_brief(bad_target)


def test_rejects_target_with_nan_dollar_amount():
    # NaN <= 0 is False, so a naive non-positive check lets a NaN
    # dollar_amount (e.g. from a sector with no valid factor score upstream)
    # through silently. This must be rejected explicitly.
    bad_target = replace(BASE_TARGET, dollar_amount=float("nan"))

    with pytest.raises(PhaseGateError, match="NaN"):
        create_brief(bad_target)


def test_rejects_target_with_empty_dimension():
    bad_target = replace(BASE_TARGET, dimension=DimensionSpec())

    with pytest.raises(PhaseGateError, match="empty dimension"):
        create_brief(bad_target)


def test_rejects_sell_target_missing_source_bucket():
    bad_target = replace(BASE_TARGET, direction=Direction.SELL, source_bucket=())

    with pytest.raises(PhaseGateError, match="source_bucket"):
        create_brief(bad_target)
