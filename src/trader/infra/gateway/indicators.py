def calculate_rsi(closes: list[float], period: int = 14) -> float | None:
    """
    Wilder's RSI: seeded with the simple mean of the first `period` moves,
    then smoothed as avg = (avg * (period - 1) + move) / period.
    Live and backtest pass the same window length, so both see the same value.
    """
    if period <= 0 or len(closes) < period + 1:
        return None

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    avg_gain = sum(max(delta, 0.0) for delta in deltas[:period]) / period
    avg_loss = sum(max(-delta, 0.0) for delta in deltas[:period]) / period

    for delta in deltas[period:]:
        avg_gain = (avg_gain * (period - 1) + max(delta, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0.0)) / period

    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
