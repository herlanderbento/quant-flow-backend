from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from ml.data.ohlcv import normalize_ohlcv
from ml.features.pipeline import (
    FEATURE_NAMES,
    WARMUP_CANDLES,
    FeatureError,
    compute_features,
    latest_features,
)
from ml.labels import LabelSpec, make_labels

HOUR_MS = 3_600_000
START_MS = 1_700_000_000_000 - (1_700_000_000_000 % HOUR_MS)


def random_walk(n=600, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    open_ = np.concatenate([[100.0], close[:-1]])
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.005, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.005, n))
    volume = rng.uniform(10, 100, n)
    rows = [[START_MS + i * HOUR_MS, open_[i], high[i], low[i], close[i], volume[i]] for i in range(n)]
    frame, _ = normalize_ohlcv(rows, "1h")
    return frame


# ---- data quality ------------------------------------------------------------------


def test_normalize_sorts_dedupes_drops_invalid_and_reports_gaps():
    rows = [
        [START_MS + 2 * HOUR_MS, 1, 2, 0.5, 1.5, 10],
        [START_MS, 1, 2, 0.5, 1.5, 10],
        [START_MS, 1, 2, 0.5, 1.6, 11],              # duplicate: last version wins
        [START_MS + HOUR_MS, 1, 0.9, 0.5, 1.5, 10],  # high below close: invalid
        [START_MS + 5 * HOUR_MS, 1, 2, 0.5, 1.5, 10],
    ]
    frame, report = normalize_ohlcv(rows, "1h")
    assert list(frame["timestamp"].astype("int64") // 1_000_000) == [
        START_MS, START_MS + 2 * HOUR_MS, START_MS + 5 * HOUR_MS]
    assert frame["close"].iloc[0] == 1.6
    assert report.duplicates_removed == 1
    assert report.invalid_removed == 1
    assert report.missing_candles == 1 + 2  # hour 1 (invalid) and hours 3-4


# ---- features: no look-ahead --------------------------------------------------------


def test_features_at_t_do_not_change_when_the_future_changes():
    frame = random_walk()
    t = 400
    base = compute_features(frame, "1h").iloc[t]

    future_changed = frame.copy()
    future_changed.loc[t + 1:, ["open", "high", "low", "close"]] *= 3.0
    future_changed.loc[t + 1:, "volume"] *= 50
    assert compute_features(future_changed, "1h").iloc[t].equals(base)

    truncated = compute_features(frame.iloc[: t + 1].copy(), "1h").iloc[t]
    pd.testing.assert_series_equal(truncated, base, check_names=False)


def test_inference_uses_the_same_computation_as_training():
    frame = random_walk()
    now = frame["timestamp"].iloc[-1] + timedelta(hours=1, minutes=1)
    vector = latest_features(frame, "1h", now.to_pydatetime())
    training_row = compute_features(frame, "1h").iloc[-1]
    for name in FEATURE_NAMES:
        assert vector.values[name] == pytest.approx(training_row[name], rel=1e-9, abs=1e-12)


def test_warmup_rows_are_nan_then_complete():
    features = compute_features(random_walk(), "1h")
    assert features.iloc[: WARMUP_CANDLES - 2].isna().any(axis=1).all()
    assert features.iloc[WARMUP_CANDLES:].notna().all(axis=None)


def test_gap_in_lookback_invalidates_features():
    frame = random_walk()
    frame = frame.drop(index=300).reset_index(drop=True)  # one missing hour
    features = compute_features(frame, "1h")
    assert features.iloc[300: 300 + WARMUP_CANDLES - 1].isna().all(axis=None)
    assert features.iloc[300 + WARMUP_CANDLES:].notna().all(axis=None)


def test_inference_refuses_stale_unclosed_or_short_history():
    frame = random_walk()
    last_open = frame["timestamp"].iloc[-1]
    with pytest.raises(FeatureError, match="not closed"):
        latest_features(frame, "1h", (last_open + timedelta(minutes=30)).to_pydatetime())
    with pytest.raises(FeatureError, match="stale"):
        latest_features(frame, "1h", (last_open + timedelta(hours=5)).to_pydatetime())
    with pytest.raises(FeatureError, match="need"):
        latest_features(frame.tail(50), "1h", (last_open + timedelta(hours=1)).to_pydatetime())


# ---- labels -------------------------------------------------------------------------


def test_label_is_the_net_return_of_the_trade_the_worker_would_place():
    frame = random_walk()
    spec = LabelSpec(horizon=12, taker_fee_rate=0.001, slippage_bps=5)
    labels = make_labels(frame, spec, "1h")
    t = 250
    entry = frame["open"].iloc[t + 1] * 1.0005
    exit_ = frame["close"].iloc[t + 12] * 0.9995
    expected = exit_ * 0.999 * 0.999 / entry - 1
    assert labels["net_return"].iloc[t] == pytest.approx(expected)
    assert labels["label"].iloc[t] == float(expected > 0)


def test_label_does_not_use_information_up_to_t():
    frame = random_walk()
    spec = LabelSpec()
    t = 250
    changed = frame.copy()
    changed.loc[:t, ["close", "high", "low"]] *= 1.5  # the past and candle t itself
    a = make_labels(frame, spec, "1h").iloc[t]
    b = make_labels(changed, spec, "1h").iloc[t]
    assert a.equals(b)


def test_labels_missing_at_the_end_and_across_gaps():
    frame = random_walk()
    spec = LabelSpec(horizon=12)
    labels = make_labels(frame, spec, "1h")
    assert labels["label"].iloc[-12:].isna().all()
    gapped = frame.drop(index=300).reset_index(drop=True)
    gap_labels = make_labels(gapped, spec, "1h")
    assert gap_labels["label"].iloc[288:300].isna().all()   # forward window crosses the gap
    assert gap_labels["label"].iloc[[287, 300]].notna().all()
