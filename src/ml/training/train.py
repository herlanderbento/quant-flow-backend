"""Train the deployable model artifact (shadow mode until a human approves it).

    python -m ml.training.train --symbol BTC/USDT --symbol ETH/USDT \
        --walk-forward-report artifacts/reports/walk_forward/report.json \
        --out-dir artifacts/models

Trains on the most recent `train_months`, chooses the model and threshold on the following
`val_months`, and records full provenance. Never trains inside the worker.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from ml.data.ohlcv import TIMEFRAME_SECONDS, dataset_path, file_sha256, load_dataset
from ml.labels import LabelSpec
from ml.models.artifact import write_artifact
from ml.training.dataset import between, build_symbol_data, matrix, pooled


def train(symbols, timeframe, root: Path, spec: LabelSpec, train_months: int, val_months: int,
          walk_forward_report: Path | None, research_shadow_only: bool = False,
          ) -> tuple[dict | None, str | None]:
    from ml.training.candidates import select_model  # sklearn is a training-only dependency

    datasets, data_provenance = [], {}
    for symbol in symbols:
        candles, quality, digest = load_dataset(dataset_path(root, symbol, timeframe), timeframe)
        datasets.append(build_symbol_data(symbol, candles, spec, timeframe))
        data_provenance[symbol] = {"sha256": digest, "quality": quality.as_dict(),
                                   "last_candle": str(candles["timestamp"].iloc[-1])}
    rows = pooled(datasets)
    purge = pd.Timedelta(seconds=TIMEFRAME_SECONDS[timeframe] * spec.horizon)
    end = rows["timestamp"].max() + pd.Timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    val_start = end - pd.DateOffset(months=val_months)
    train_start = val_start - pd.DateOffset(months=train_months)
    train_rows = between(rows, train_start, val_start, purge)
    val_rows = between(rows, val_start, end)
    tx, ty = matrix(train_rows)
    vx, vy = matrix(val_rows)

    evaluation = None
    if walk_forward_report is not None:
        report = json.loads(walk_forward_report.read_text(encoding="utf-8"))
        evaluation = {"walk_forward_report_sha256": file_sha256(walk_forward_report),
                      "walk_forward_aggregate": report.get("aggregate")}

    selection = select_model(tx, ty, vx, vy, val_rows["net_return"].to_numpy(), {
        "timeframe": timeframe,
        "symbols": symbols,
        "label_spec": spec.as_dict(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "training": {"train": [str(train_start), str(val_start)],
                     "validation": [str(val_start), str(end)],
                     "train_rows": int(len(train_rows)), "validation_rows": int(len(val_rows)),
                     "data": data_provenance},
        "evaluation": evaluation,
        "approval": {"approved_for_trading": False, "approved_by": None,
                     "reason": "not validated: shadow mode only"},
    }, research_shadow_only=research_shadow_only)
    return selection.document, selection.reason


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", action="append", required=True)
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--root", type=Path, default=Path("data/ml/ohlcv"))
    parser.add_argument("--out-dir", type=Path, default=Path("artifacts/models"))
    parser.add_argument("--train-months", type=int, default=12)
    parser.add_argument("--val-months", type=int, default=3)
    parser.add_argument("--walk-forward-report", type=Path, default=None)
    parser.add_argument("--research-shadow-only", action="store_true",
                        help="write the best candidate even without validated edge, "
                             "marked validation_failed (shadow logging only, never approvable)")
    args = parser.parse_args()

    document, reason = train(args.symbol, args.timeframe, args.root, LabelSpec(),
                             args.train_months, args.val_months, args.walk_forward_report,
                             args.research_shadow_only)
    if document is None:
        print(f"No artifact written: {reason}")
        raise SystemExit(1)
    path = args.out_dir / f"{document['model_version']}.json"
    digest = write_artifact(document, path)
    print(f"model {document['model_version']} ({document['kind']}) "
          f"buy>={document['decision']['buy_threshold']} sell<={document['decision']['sell_threshold']}")
    print(f"saved {path} sha256={digest} approved_for_trading=False")
    if document.get("validation_failed"):
        print(f"RESEARCH/SHADOW ONLY: {document['validation_failed']}")


if __name__ == "__main__":
    main()
