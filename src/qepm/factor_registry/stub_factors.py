"""Stub factors exercising the registration mechanism - not real, PM-approved factor definitions."""

from __future__ import annotations

import pandas as pd

from qepm.contracts import FactorDefinition, Snapshot


def _momentum_formula(snapshot: Snapshot) -> pd.Series:
    return snapshot.securities["momentum_raw"].astype(float)


STUB_MOMENTUM = FactorDefinition(
    name="momentum",
    formula=_momentum_formula,
    weight=1.0,
    description="Stub factor: raw trailing momentum, unweighted.",
    required_fields=("momentum_raw",),
)


def _macro_adjusted_momentum_formula(snapshot: Snapshot) -> pd.Series:
    risk_free_rate = snapshot.macro.loc[snapshot.as_of, "risk_free_rate"]
    return snapshot.securities["momentum_raw"].astype(float) - risk_free_rate


STUB_MACRO_ADJUSTED_MOMENTUM = FactorDefinition(
    name="macro_adjusted_momentum",
    formula=_macro_adjusted_momentum_formula,
    weight=1.0,
    description="Stub factor: momentum in excess of the macro risk-free rate - exercises a formula reading the macro series, not just the per-security panel.",
    required_fields=("momentum_raw",),
    required_macro_fields=("risk_free_rate",),
)
