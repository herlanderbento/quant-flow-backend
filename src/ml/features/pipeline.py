"""
Feature pipeline v1. Row t uses only candles with open time <= t (all closed when used).
Training and inference call the same function; inference keeps the last row.
"""
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from ml.data.ohlcv import TIMEFRAME_SECONDS
from trader.infra.gateway.indicators import calculate_rsi

FEATURE_SCHEMA_VERSION = "v1"
RSI_PERIOD = 14
RSI_WINDOW = RSI_PERIOD + 51  # same window the live snapshot uses
LONGEST_LOOKBACK = 169  # vol_ratio needs 168 one-candle returns
WARMUP_CANDLES = LONGEST_LOOKBACK + 1

FEATURE_NAMES = [
    "ret_1", "ret_3", "ret_6", "ret_12", "ret_24", "ret_72",
    "rsi_14",
    "vol_12", "vol_48", "vol_ratio_12_168",
    "range_12", "atr_14_pct", "close_pos_12",
    "volume_log_ratio_24", "volume_z_48",
    "sma_dev_24", "sma_dev_72", "sma_cross_12_48",
]


class FeatureError(ValueError):
    """Features cannot be trusted for this prediction (stale, missing, gap, invalid)."""


def _rolling_rsi(close: pd.Series) -> pd.Series:
    values = close.to_numpy()
    out = np.full(len(values), np.nan)
    for i in range(RSI_WINDOW - 1, len(values)):
        rsi = calculate_rsi(list(values[i - RSI_WINDOW + 1: i + 1]), RSI_PERIOD)
        out[i] = np.nan if rsi is None else rsi
    return pd.Series(out, index=close.index)


def compute_features(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Feature table aligned with `frame` (NaN where history is short or spans a gap)."""
    close, high, low, volume = frame["close"], frame["high"], frame["low"], frame["volume"]
    log_close = np.log(close)
    r1 = log_close.diff()

    f = pd.DataFrame(index=frame.index)
    for k in (1, 3, 6, 12, 24, 72):
        f[f"ret_{k}"] = log_close - log_close.shift(k)
    f["rsi_14"] = _rolling_rsi(close)
    f["vol_12"] = r1.rolling(12).std()
    f["vol_48"] = r1.rolling(48).std()
    f["vol_ratio_12_168"] = f["vol_12"] / r1.rolling(168).std()
    f["range_12"] = ((high - low) / close).rolling(12).mean()
    previous_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1
    ).max(axis=1)
    f["atr_14_pct"] = true_range.rolling(14).mean() / close
    low_12, high_12 = low.rolling(12).min(), high.rolling(12).max()
    f["close_pos_12"] = (close - low_12) / (high_12 - low_12).replace(0, np.nan)
    f["volume_log_ratio_24"] = np.log((volume + 1e-12) / (volume.rolling(24).mean() + 1e-12))
    f["volume_z_48"] = (volume - volume.rolling(48).mean()) / volume.rolling(48).std().replace(0, np.nan)
    sma_12, sma_24 = close.rolling(12).mean(), close.rolling(24).mean()
    sma_48, sma_72 = close.rolling(48).mean(), close.rolling(72).mean()
    f["sma_dev_24"] = close / sma_24 - 1
    f["sma_dev_72"] = close / sma_72 - 1
    f["sma_cross_12_48"] = sma_12 / sma_48 - 1

    # Invalidate rows whose lookback window crosses a gap in the data.
    step = pd.Timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    broken = (frame["timestamp"].diff() != step).astype(float)
    broken.iloc[0] = 0.0
    crosses_gap = broken.rolling(WARMUP_CANDLES, min_periods=1).sum() > 0
    f.loc[crosses_gap] = np.nan
    f = f.replace([np.inf, -np.inf], np.nan)
    return f[FEATURE_NAMES]


@dataclass(frozen=True)
class FeatureVector:
    values: dict[str, float]
    candle_open_time: datetime  # open time of the last closed candle used
    candle_close_time: datetime
    schema_version: str = FEATURE_SCHEMA_VERSION


def latest_features(frame: pd.DataFrame, timeframe: str, now: datetime,
                    max_staleness_periods: int = 2) -> FeatureVector:
    """Features of the last closed candle, or FeatureError if they cannot be trusted."""
    if len(frame) < WARMUP_CANDLES:
        raise FeatureError(f"need {WARMUP_CANDLES} closed candles, got {len(frame)}")
    period = pd.Timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    last_open = frame["timestamp"].iloc[-1]
    last_close = last_open + period
    if last_close > pd.Timestamp(now):
        raise FeatureError("last candle is not closed yet")
    if pd.Timestamp(now) - last_close > period * max_staleness_periods:
        raise FeatureError(f"stale data: last candle closed at {last_close}")

    row = compute_features(frame.tail(WARMUP_CANDLES).reset_index(drop=True), timeframe).iloc[-1]
    if row.isna().any():
        missing = [name for name in FEATURE_NAMES if pd.isna(row[name])]
        raise FeatureError(f"invalid features (gap or missing data): {missing}")
    return FeatureVector(
        values={name: float(row[name]) for name in FEATURE_NAMES},
        candle_open_time=last_open.to_pydatetime(),
        candle_close_time=last_close.to_pydatetime(),
    )
