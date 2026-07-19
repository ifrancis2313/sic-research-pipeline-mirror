"""QEPM: SIC's factor-driven equity research pipeline.

Six original PRD modules: universe_data_store, factor_registry,
exposure_optimizer, research_brief_tracker, legacy backtest_gate, and
trade_execution. V1 callers use portfolio_fit for the same-snapshot control;
backtest_gate remains only to preserve the original walking skeleton.
"""
