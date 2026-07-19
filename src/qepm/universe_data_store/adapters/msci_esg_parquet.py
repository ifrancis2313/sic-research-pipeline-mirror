"""Adapter for MSCI ESG data, shaped like Data/msci.parquet / Data/fullpanelmsci.parquet.

Bulk, per-security, keyed by (issuerid, as_of_date) with ISIN/CUSIP/SEDOL
identifiers - crosswalks via ISIN (populated for ~98% of rows here, far
more complete than CUSIP) into FIGI, inside this adapter, per CONTEXT.md.

Only a handful of headline ESG fields are carried over, not all ~250
MSCI columns - add more to ESG_COLUMN_MAP as a later pitch/need arises,
same adapter, no framework change.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from qepm.universe_data_store.adapters.base import Adapter, AdapterOutput

ESG_COLUMN_MAP = {
    "weighted_average_score": "esg_score",
    "iva_company_rating": "esg_rating",
    "environmental_pillar_score": "esg_environmental",
    "social_pillar_score": "esg_social",
    "governance_pillar_score": "esg_governance",
}


class MsciEsgAdapter(Adapter):
    name = "msci_esg_parquet"

    def __init__(self, isin_to_figi: dict[str, str]) -> None:
        self.isin_to_figi = isin_to_figi

    def load(self, source: Any) -> AdapterOutput:
        raw = pd.read_parquet(source)
        raw = raw.dropna(subset=["issuer_isin"])
        raw = raw[raw["issuer_isin"].isin(self.isin_to_figi)]
        if raw.empty:
            raise ValueError(
                "no rows resolved to a FIGI via the isin_to_figi crosswalk - "
                "is the crosswalk populated for any ISIN in this file?"
            )

        present_columns = [c for c in ESG_COLUMN_MAP if c in raw.columns]
        panel = raw[["issuer_isin", "as_of_date"] + present_columns].rename(columns=ESG_COLUMN_MAP)
        panel["figi"] = panel["issuer_isin"].map(self.isin_to_figi)
        panel["date"] = pd.to_datetime(panel["as_of_date"]).dt.date
        panel = (
            panel.drop(columns=["issuer_isin", "as_of_date"])
            .set_index(["figi", "date"])
            .sort_index()
        )

        return AdapterOutput(panel=panel)
