from qepm.portfolio_fit import evaluate_portfolio_fit


def test_portfolio_fit_is_available_under_its_v1_public_name():
    assert callable(evaluate_portfolio_fit)
