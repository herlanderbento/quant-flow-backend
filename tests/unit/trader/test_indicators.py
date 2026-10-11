import pytest

from trader.infra.gateway.indicators import calculate_rsi

# Reference series and value from J. Welles Wilder's RSI worked example
# as reproduced by StockCharts ("RSI" ChartSchool article): first RSI = 70.53.
STOCKCHARTS_CLOSES = [
    44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245,
    45.8433, 46.0826, 45.8931, 46.0328, 45.6140, 46.2820, 46.2820,
]
STOCKCHARTS_NEXT = [46.0028, 46.0328, 46.4116, 46.2222, 45.6439, 46.2122]
STOCKCHARTS_RSI = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97, 62.93]


def test_first_value_matches_reference():
    assert calculate_rsi(STOCKCHARTS_CLOSES, 14) == pytest.approx(STOCKCHARTS_RSI[0], abs=0.01)


def test_wilder_smoothing_matches_reference_series():
    closes = list(STOCKCHARTS_CLOSES)
    for close, expected in zip(STOCKCHARTS_NEXT, STOCKCHARTS_RSI[1:]):
        closes.append(close)
        assert calculate_rsi(closes, 14) == pytest.approx(expected, abs=0.01)


def test_not_enough_data():
    assert calculate_rsi([1.0] * 14, 14) is None


def test_flat_series_is_neutral_and_rising_series_is_100():
    assert calculate_rsi([10.0] * 20, 14) == 50.0
    assert calculate_rsi([float(i) for i in range(20)], 14) == 100.0
