import pytest

from qepm.universe_data_store.adapters.single_ticker_excel import SingleTickerExcelAdapter
from qepm.universe_data_store.gate import validate_adapter_output


def test_extracts_ticker_from_title_cell_and_crosswalks_to_figi(data_dir):
    adapter = SingleTickerExcelAdapter(ticker_to_figi={"SPX": "FIGI-TEST-SPX"})

    output = adapter.load(data_dir / "PriceHistory.xlsx")

    figis = output.panel.index.get_level_values("figi").unique()
    assert list(figis) == ["FIGI-TEST-SPX"]


def test_handles_sparse_columns_without_requiring_them(data_dir):
    adapter = SingleTickerExcelAdapter(ticker_to_figi={"SPX": "FIGI-TEST-SPX"})

    output = adapter.load(data_dir / "PriceHistory.xlsx")

    assert "total_return" in output.panel.columns
    assert output.panel["total_return"].isna().all()  # sparse in this export - present, not required
    assert output.panel["price"].notna().all()  # a required-in-practice column is fully populated


def test_output_passes_phase_1_gate(data_dir):
    adapter = SingleTickerExcelAdapter(ticker_to_figi={"SPX": "FIGI-TEST-SPX"})

    output = adapter.load(data_dir / "PriceHistory.xlsx")

    validate_adapter_output(output)  # raises on failure


def test_unrecognized_ticker_raises_a_clear_error(data_dir):
    adapter = SingleTickerExcelAdapter(ticker_to_figi={})

    with pytest.raises(ValueError, match="SPX"):
        adapter.load(data_dir / "PriceHistory.xlsx")
