import pytest

from qepm.universe_data_store.adapters.msci_esg_parquet import MsciEsgAdapter
from qepm.universe_data_store.gate import validate_adapter_output


def test_crosswalks_via_isin_and_carries_headline_esg_fields(data_dir):
    adapter = MsciEsgAdapter(isin_to_figi={"US0000000101": "FIGI-TEST-A"})

    output = adapter.load(data_dir / "msci.parquet")

    figis = output.panel.index.get_level_values("figi").unique()
    assert list(figis) == ["FIGI-TEST-A"]
    assert {"esg_score", "esg_rating", "esg_environmental", "esg_social", "esg_governance"} <= set(
        output.panel.columns
    )


def test_rows_with_no_crosswalk_entry_are_excluded_not_force_fit(data_dir):
    adapter = MsciEsgAdapter(
        isin_to_figi={"US0000000101": "FIGI-TEST-A", "US0000000102": "FIGI-TEST-B"}
    )

    output = adapter.load(data_dir / "msci.parquet")

    figis = set(output.panel.index.get_level_values("figi"))
    assert figis == {"FIGI-TEST-A", "FIGI-TEST-B"}


def test_raises_when_no_row_resolves_via_the_crosswalk(data_dir):
    adapter = MsciEsgAdapter(isin_to_figi={"US0000000000": "FIGI-NOBODY"})

    with pytest.raises(ValueError, match="crosswalk"):
        adapter.load(data_dir / "msci.parquet")


def test_output_passes_phase_1_gate(data_dir):
    adapter = MsciEsgAdapter(isin_to_figi={"US0000000101": "FIGI-TEST-A"})

    output = adapter.load(data_dir / "msci.parquet")

    validate_adapter_output(output)  # raises on failure
