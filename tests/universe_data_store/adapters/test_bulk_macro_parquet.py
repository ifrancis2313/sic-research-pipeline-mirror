import pytest

from qepm.contracts import PhaseGateError
from qepm.universe_data_store.adapters.bulk_macro_parquet import BulkMacroParquetAdapter
from qepm.universe_data_store.gate import validate_adapter_output
from qepm.universe_data_store.schema import is_macro_shaped


def test_parses_bulk_fama_french_file_into_macro_shape(data_dir):
    adapter = BulkMacroParquetAdapter()

    output = adapter.load(data_dir / "ff5.parquet")

    assert output.panel is None
    assert is_macro_shaped(output.macro)
    assert list(output.macro.columns) == ["mktrf", "smb", "hml", "rmw", "cma", "rf", "umd"]
    assert len(output.macro) > 15_000


def test_output_passes_phase_1_gate(data_dir):
    adapter = BulkMacroParquetAdapter()

    output = adapter.load(data_dir / "ff5.parquet")

    validate_adapter_output(output)  # raises on failure


def test_rejects_cboe_source_with_duplicate_macro_dates(data_dir):
    # CBOE's raw history has duplicate dates with conflicting populated values.
    # It remains non-trading research input until the source issue is reconciled.
    adapter = BulkMacroParquetAdapter(name="cboe_vix", date_column="Date")

    output = adapter.load(data_dir / "cboeall1986.parquet")

    assert adapter.name == "cboe_vix"
    assert is_macro_shaped(output.macro)
    assert "vix" in output.macro.columns
    with pytest.raises(PhaseGateError, match="duplicate macro dates"):
        validate_adapter_output(output)


def test_same_adapter_class_handles_the_three_factor_fama_french_file(data_dir):
    # Data/ff3.parquet is shaped identically to ff5.parquet (just missing rmw/cma) -
    # another zero-new-code instance, distinctly named so it doesn't collide with
    # the already-registered "ff5_fama_french" source.
    adapter = BulkMacroParquetAdapter(name="ff3_fama_french")

    output = adapter.load(data_dir / "ff3.parquet")

    assert adapter.name == "ff3_fama_french"
    assert is_macro_shaped(output.macro)
    assert list(output.macro.columns) == ["mktrf", "smb", "hml", "rf", "umd"]
    assert len(output.macro) > 25_000
    validate_adapter_output(output)  # raises on failure
