from datetime import date

import numpy as np
import pandas as pd
import pytest

from qepm.contracts import PhaseGateError, Snapshot
from qepm.factor_registry import score_universe
from qepm.factor_registry.v1 import v1_factor_registry


def test_v1_scores_value_and_quality_within_sector_and_momentum_across_universe():
    securities = pd.DataFrame(
        {
            "figi": ["TECH-LOW", "TECH-HIGH", "ENERGY-LOW", "ENERGY-HIGH"],
            "sector": ["Technology", "Technology", "Energy", "Energy"],
            "free_cash_flow_ttm": [10.0, 30.0, 40.0, 100.0],
            "market_cap": [1_000.0, 1_000.0, 2_000.0, 2_000.0],
            "revenue_ttm": [100.0, 100.0, 100.0, 100.0],
            "cost_of_revenue_ttm": [80.0, 40.0, 90.0, 20.0],
            "total_assets": [100.0, 100.0, 100.0, 100.0],
            "momentum_12_1": [0.10, 0.40, 0.20, 0.30],
        }
    ).set_index("figi")
    snapshot = Snapshot(
        as_of=date(2026, 7, 17),
        securities=securities,
        macro=pd.DataFrame(index=pd.Index([], name="date")),
    )

    scores = score_universe(snapshot, v1_factor_registry())

    assert scores.scores.loc["TECH-LOW", "value"] == 50.0
    assert scores.scores.loc["TECH-HIGH", "value"] == 100.0
    assert scores.scores.loc["ENERGY-LOW", "quality"] == 50.0
    assert scores.scores.loc["ENERGY-HIGH", "quality"] == 100.0
    assert scores.scores.loc["TECH-LOW", "momentum"] == 25.0
    assert scores.scores.loc["TECH-HIGH", "momentum"] == 100.0
    assert scores.weights == {"value": 1.0, "quality": 1.0, "momentum": 1.0, "size": 0.0}


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("market_cap", 0.0, "market_cap"),
        ("market_cap", -1.0, "market_cap"),
        ("market_cap", np.inf, "non-finite"),
        ("total_assets", 0.0, "total_assets"),
        ("total_assets", -1.0, "total_assets"),
        ("momentum_12_1", "not-a-number", "numeric"),
    ],
)
def test_v1_rejects_invalid_factor_inputs(column, value, message):
    securities = pd.DataFrame(
        {
            "figi": ["F1"],
            "sector": ["Technology"],
            "free_cash_flow_ttm": [10.0],
            "market_cap": [100.0],
            "revenue_ttm": [100.0],
            "cost_of_revenue_ttm": [50.0],
            "total_assets": [100.0],
            "momentum_12_1": [0.10],
        }
    ).set_index("figi")
    if isinstance(value, str):
        securities[column] = securities[column].astype(object)
    securities.loc["F1", column] = value
    snapshot = Snapshot(date(2026, 7, 17), securities, pd.DataFrame(index=pd.Index([], name="date")))

    with pytest.raises(PhaseGateError, match=message):
        score_universe(snapshot, v1_factor_registry())


def test_v1_accepts_negative_free_cash_flow_as_an_economically_valid_value():
    securities = pd.DataFrame(
        {
            "figi": ["F1", "F2"],
            "sector": ["Technology", "Technology"],
            "free_cash_flow_ttm": [-10.0, 10.0],
            "market_cap": [100.0, 100.0],
            "revenue_ttm": [100.0, 100.0],
            "cost_of_revenue_ttm": [50.0, 50.0],
            "total_assets": [100.0, 100.0],
            "momentum_12_1": [0.10, 0.20],
        }
    ).set_index("figi")
    snapshot = Snapshot(date(2026, 7, 17), securities, pd.DataFrame(index=pd.Index([], name="date")))

    scores = score_universe(snapshot, v1_factor_registry())

    assert scores.scores.loc["F1", "value"] == 50.0


def test_v1_missing_factor_input_remains_na_instead_of_becoming_a_finite_score():
    securities = pd.DataFrame(
        {
            "figi": ["F1", "F2"], "sector": ["Technology", "Technology"],
            "free_cash_flow_ttm": [10.0, 20.0], "market_cap": [100.0, 100.0],
            "revenue_ttm": [100.0, 100.0], "cost_of_revenue_ttm": [50.0, 50.0],
            "total_assets": [100.0, 100.0], "momentum_12_1": [float("nan"), 0.2],
        }
    ).set_index("figi")

    scores = score_universe(
        Snapshot(date(2026, 7, 17), securities, pd.DataFrame(index=pd.Index([], name="date"))),
        v1_factor_registry(),
    )

    assert pd.isna(scores.scores.loc["F1", "momentum"])


def test_v1_sector_relative_factors_are_na_without_a_sector_peer():
    securities = pd.DataFrame(
        {
            "figi": ["F1", "F2", "F3"],
            "sector": ["Technology", "Technology", "Utilities"],
            "free_cash_flow_ttm": [10.0, 20.0, 30.0],
            "market_cap": [100.0, 100.0, 100.0],
            "revenue_ttm": [100.0, 100.0, 100.0],
            "cost_of_revenue_ttm": [50.0, 40.0, 30.0],
            "total_assets": [100.0, 100.0, 100.0],
            "momentum_12_1": [0.1, 0.2, 0.3],
        }
    ).set_index("figi")

    scores = score_universe(
        Snapshot(date(2026, 7, 17), securities, pd.DataFrame(index=pd.Index([], name="date"))),
        v1_factor_registry(),
    )

    assert pd.isna(scores.scores.loc["F3", "value"])
    assert pd.isna(scores.scores.loc["F3", "quality"])


def test_v1_factor_registry_declares_the_exact_required_fields_per_factor():
    """`required_fields` is what the Data -> Factor gate actually enforces
    before scoring runs (see gate.py); an omitted or wrong tuple here would
    silently let a factor score against missing input data instead of
    failing closed. No other test asserts on these tuples directly."""
    registry = v1_factor_registry()

    assert registry.get("value").required_fields == ("sector", "free_cash_flow_ttm", "market_cap")
    assert registry.get("value").weight == 1.0
    assert registry.get("quality").required_fields == (
        "sector",
        "revenue_ttm",
        "cost_of_revenue_ttm",
        "total_assets",
    )
    assert registry.get("quality").weight == 1.0
    assert registry.get("momentum").required_fields == ("momentum_12_1",)
    assert registry.get("momentum").weight == 1.0
    assert registry.get("size").required_fields == ("market_cap",)
    assert registry.get("size").weight == 0.0
