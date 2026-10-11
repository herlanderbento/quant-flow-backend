import pytest

from ml.evaluation.walk_forward import aggregate


def _symbol(ret, bh):
    run = {"return_pct": ret, "max_drawdown_pct": 0.0, "sharpe": None, "_pnls": [ret],
           "trades": 1, "exposure_pct": 0.0, "fees": 0.0}
    return {"regime": "range", "hourly_volatility": 0.01, "ml": run, "rsi": run,
            "buy_and_hold_pct": bh, "no_trade_pct": 0.0}


def test_compounding_splits_capital_across_symbols_of_the_same_period():
    folds = [
        {"symbols": {"BTC": _symbol(10.0, 10.0), "ETH": _symbol(-10.0, -10.0)}},
        {"symbols": {"BTC": _symbol(20.0, 20.0), "ETH": _symbol(0.0, 0.0)}},
    ]
    out = aggregate(folds)["buy_and_hold"]
    # 50/50 per period: 0 % then +10 % -> +10 %. Chaining all four would give -4.96 %.
    assert out["compounded_return_pct_equal_split"] == pytest.approx(10.0)
    assert out["windows"] == 4
    assert out["test_periods"] == 2
    assert out["mean_window_return_pct"] == pytest.approx(5.0)
