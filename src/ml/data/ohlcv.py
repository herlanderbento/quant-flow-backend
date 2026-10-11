"""OHLCV datasets: normalization, quality report and reproducible on-disk storage."""
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
TIMEFRAME_SECONDS = {"15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


@dataclass(frozen=True)
class DataQualityReport:
    rows_in: int
    rows_out: int
    duplicates_removed: int
    invalid_removed: int
    gaps: list[tuple[str, str, int]] = field(default_factory=list)  # (after, before, missing)

    @property
    def missing_candles(self) -> int:
        return sum(missing for _, _, missing in self.gaps)

    def as_dict(self) -> dict:
        return {
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "duplicates_removed": self.duplicates_removed,
            "invalid_removed": self.invalid_removed,
            "gap_count": len(self.gaps),
            "missing_candles": self.missing_candles,
            "largest_gaps": sorted(self.gaps, key=lambda g: -g[2])[:5],
        }


def normalize_ohlcv(rows, timeframe: str) -> tuple[pd.DataFrame, DataQualityReport]:
    """
    Sort chronologically, drop duplicate timestamps (keep the last version), drop invalid
    candles and report gaps. Gaps are not filled: features spanning a gap are invalidated.
    `timestamp` is the candle OPEN time in UTC.
    """
    frame = pd.DataFrame(list(rows), columns=COLUMNS) if not isinstance(rows, pd.DataFrame) else rows.copy()
    rows_in = len(frame)
    if not pd.api.types.is_datetime64_any_dtype(frame["timestamp"]):
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True)
    for column in COLUMNS[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.sort_values("timestamp", kind="stable")
    before = len(frame)
    frame = frame.drop_duplicates("timestamp", keep="last")
    duplicates = before - len(frame)

    prices = frame[["open", "high", "low", "close"]]
    valid = (
        prices.notna().all(axis=1)
        & (prices > 0).all(axis=1)
        & (frame["high"] >= frame[["open", "close", "low"]].max(axis=1))
        & (frame["low"] <= frame[["open", "close", "high"]].min(axis=1))
        & frame["volume"].notna()
        & (frame["volume"] >= 0)
    )
    invalid = int((~valid).sum())
    frame = frame[valid].reset_index(drop=True)

    step = pd.Timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    deltas = frame["timestamp"].diff()
    gaps = [
        (str(frame["timestamp"].iloc[i - 1]), str(frame["timestamp"].iloc[i]), int(deltas.iloc[i] / step) - 1)
        for i in np.flatnonzero((deltas > step).to_numpy())
    ]
    report = DataQualityReport(rows_in, len(frame), duplicates, invalid, gaps)
    return frame, report


def dataset_path(root: Path, symbol: str, timeframe: str, exchange: str = "bybit") -> Path:
    return root / f"{exchange}_{symbol.replace('/', '').lower()}_{timeframe}.csv"


def save_dataset(frame: pd.DataFrame, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = frame.copy()
    out["timestamp"] = (out["timestamp"].astype("int64") // 1_000_000).astype("int64")
    out.to_csv(path, index=False, columns=COLUMNS)
    return file_sha256(path)


def load_dataset(path: Path, timeframe: str) -> tuple[pd.DataFrame, DataQualityReport, str]:
    raw = pd.read_csv(path)
    frame, report = normalize_ohlcv(raw, timeframe)
    return frame, report, file_sha256(path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
