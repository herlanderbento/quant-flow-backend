"""
Prediction target v1.

For the closed candle t, a long trade is simulated exactly as the live worker would place it:
buy at the OPEN of candle t+1 (slippage + taker fee), sell at the CLOSE of candle t+horizon
(slippage + taker fee). label = 1 when that net return is above `min_edge`.
Rows whose forward window is incomplete or crosses a data gap get NaN.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.data.ohlcv import TIMEFRAME_SECONDS


@dataclass(frozen=True)
class LabelSpec:
    horizon: int = 12
    taker_fee_rate: float = 0.001
    slippage_bps: float = 5.0
    min_edge: float = 0.0

    @property
    def round_trip_cost(self) -> float:
        return 2 * (self.taker_fee_rate + self.slippage_bps / 10_000)

    def as_dict(self) -> dict:
        return {"horizon": self.horizon, "taker_fee_rate": self.taker_fee_rate,
                "slippage_bps": self.slippage_bps, "min_edge": self.min_edge}


def net_forward_returns(frame: pd.DataFrame, spec: LabelSpec, timeframe: str) -> pd.Series:
    slip = spec.slippage_bps / 10_000
    fee = spec.taker_fee_rate
    entry = frame["open"].shift(-1) * (1 + slip)
    exit_ = frame["close"].shift(-spec.horizon) * (1 - slip)
    net = (exit_ * (1 - fee) * (1 - fee)) / entry - 1

    step = pd.Timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    broken = (frame["timestamp"].diff() != step).astype(float)
    broken.iloc[0] = 0.0
    # A gap anywhere in (t, t+horizon] invalidates the label.
    forward_gap = broken[::-1].rolling(spec.horizon, min_periods=1).sum()[::-1].shift(-1) > 0
    net[forward_gap.fillna(True)] = np.nan
    return net


def make_labels(frame: pd.DataFrame, spec: LabelSpec, timeframe: str) -> pd.DataFrame:
    net = net_forward_returns(frame, spec, timeframe)
    label = (net > spec.min_edge).astype(float)
    label[net.isna()] = np.nan
    return pd.DataFrame({"net_return": net, "label": label}, index=frame.index)
