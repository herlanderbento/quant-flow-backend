import pytest

from trader.domain.interface.exchange_gateway_interface import TradingRules

RULES = TradingRules(amount_step=0.001, min_amount=0.001, min_cost=5.0, max_amount=2.0, max_cost=10_000.0)


def test_quantity_within_limits_is_only_floored_to_the_step():
    assert RULES.limit_quantity(0.12345, 1000.0) == pytest.approx(0.123)


def test_quantity_is_capped_by_the_maximum_amount():
    assert RULES.limit_quantity(5.0, 1000.0) == pytest.approx(2.0)


def test_quantity_is_capped_by_the_maximum_order_value():
    # 10 000 / 6 000 = 1.6666… -> floored to 1.666
    assert RULES.limit_quantity(1.9, 6000.0) == pytest.approx(1.666)


def test_missing_maximums_leave_the_quantity_unchanged():
    rules = TradingRules(amount_step=0.001, min_amount=None, min_cost=None)
    assert rules.limit_quantity(123.4567, 1.0) == pytest.approx(123.456)
