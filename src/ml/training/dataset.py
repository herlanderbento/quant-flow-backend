from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.features.pipeline import FEATURE_NAMES, compute_features
from ml.labels import LabelSpec, make_labels


@dataclass
class SymbolData:
    symbol: str
    candles: pd.DataFrame  # normalized OHLCV
    rows: pd.DataFrame     # features + label + net_return + timestamp, valid rows only


def build_symbol_data(symbol: str, candles: pd.DataFrame, spec: LabelSpec, timeframe: str) -> SymbolData:
    features = compute_features(candles, timeframe)
    labels = make_labels(candles, spec, timeframe)
    rows = pd.concat([candles[["timestamp"]], features, labels], axis=1)
    rows["symbol"] = symbol
    rows = rows.dropna(subset=FEATURE_NAMES + ["label"]).reset_index(drop=True)
    return SymbolData(symbol, candles, rows)


def pooled(datasets: list[SymbolData]) -> pd.DataFrame:
    return pd.concat([d.rows for d in datasets], ignore_index=True).sort_values(
        ["timestamp", "symbol"], kind="stable").reset_index(drop=True)


def between(rows: pd.DataFrame, start, end, purge: pd.Timedelta | None = None) -> pd.DataFrame:
    """
    Rows with start <= t < end. With `purge`, rows whose label window reaches past `end`
    (t > end - purge) are dropped, so no training label overlaps the next segment.
    """
    upper = end - purge if purge is not None else end
    mask = (rows["timestamp"] >= start) & (rows["timestamp"] < upper)
    return rows[mask]


def matrix(rows: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    return rows[FEATURE_NAMES].to_numpy(dtype=np.float64), rows["label"].to_numpy(dtype=int)
