"""Hand-built fixture universe for the walking skeleton.

Not vendor-sourced (no Bloomberg/FactSet call here) - a tiny, fixed set of
FIGI-keyed securities used to prove the pipeline's phases wire together
correctly before any real data adapter exists. Real adapters are added
behind this same interface as new data sources come online.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from qepm.contracts import Snapshot


def fixture_snapshot(as_of: date) -> Snapshot:
    securities = pd.DataFrame(
        {
            "figi": [
                "BBG-FIXTURE-001",  # tech-sector fixture
                "BBG-FIXTURE-009",  # consumer-staples fixture
                "BBG-FIXTURE-007",  # energy-sector fixture
                "BBG-FIXTURE-005",  # industrials-sector fixture
                "BBG-FIXTURE-012",  # materials-sector fixture
            ],
            "sector": ["Technology", "Consumer Staples", "Energy", "Industrials", "Materials"],
            "momentum_raw": [0.18, 0.02, 0.11, -0.04, -0.09],
            "fcf_yield": [0.032, 0.041, 0.058, 0.021, 0.015],
            "price": [190.0, 155.0, 118.0, 340.0, 42.0],
            "has_price_history": [True, True, True, True, True],
            # Fixture targets model the standard active sleeve.  Real runs
            # require point-in-time membership from the licensed data source.
            "is_russell_1000": [True, True, True, True, True],
        }
    ).set_index("figi")

    macro = pd.DataFrame(
        {"date": [as_of], "risk_free_rate": [0.045]}
    ).set_index("date")

    return Snapshot(as_of=as_of, securities=securities, macro=macro)


def fixture_holdings(as_of: date):
    from qepm.contracts import Holdings

    positions = pd.DataFrame(
        {
            "figi": [
                "BBG-FIXTURE-001",
                "BBG-FIXTURE-009",
                "BBG-FIXTURE-007",
                "BBG-FIXTURE-005",
            ],
            "dollar_value": [28_000.0, 12_000.0, 9_000.0, 15_000.0],
        }
    ).set_index("figi")

    return Holdings(as_of=as_of, positions=positions)
