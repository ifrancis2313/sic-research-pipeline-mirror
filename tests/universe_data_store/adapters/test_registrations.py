from qepm.universe_data_store.adapters import registered_adapters
from qepm.universe_data_store.adapters.registrations import register_known_sources


def test_register_known_sources_populates_the_registry_additively():
    register_known_sources()

    adapters = registered_adapters()
    assert {
        "single_ticker_excel",
        "ff5_fama_french",
        "ff3_fama_french",
        "cboe_vix",
        "msci_esg_parquet",
    } <= set(adapters)
