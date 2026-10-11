"""
Walk-forward comparison: ML strategy vs RSI vs buy & hold vs no trading.

    python -m ml.evaluation.walk_forward --symbol BTC/USDT --symbol ETH/USDT \
        --out artifacts/reports/walk_forward

Every number comes from out-of-sample test windows. Models and thresholds are chosen on
validation windows only; test results never feed back into any choice.
"""
import argparse
import asyncio
import json
import statistics
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ml.data.ohlcv import TIMEFRAME_SECONDS, dataset_path, load_dataset
from ml.features.pipeline import FEATURE_NAMES, FEATURE_SCHEMA_VERSION, WARMUP_CANDLES
from ml.inference.strategy import MLSignalStrategy
from ml.labels import LabelSpec
from ml.models.artifact import ModelPredictor
from ml.training.candidates import classification_metrics, select_model
from ml.training.dataset import between, build_symbol_data, matrix, pooled
from trader.application.backtest_engine import BacktestCosts, OhlcvCandle, run_backtest
from trader.domain.strategies.simple_rsi_strategy import SimpleRsiStrategy

STOP_LOSS_PCT = 2.0
TAKE_PROFIT_PCT = 4.0
CAPITAL = 1000.0


def month_starts(first: pd.Timestamp, last: pd.Timestamp) -> list[pd.Timestamp]:
    start = (first + pd.offsets.MonthBegin(1)).normalize()
    return list(pd.date_range(start, last, freq="MS", tz="UTC"))


def to_candles(frame: pd.DataFrame) -> list[OhlcvCandle]:
    return [
        OhlcvCandle(row.timestamp.to_pydatetime(), row.open, row.high, row.low, row.close, row.volume)
        for row in frame.itertuples(index=False)
    ]


def regime(bh_return_pct: float) -> str:
    if bh_return_pct > 5:
        return "bull"
    if bh_return_pct < -5:
        return "bear"
    return "range"


async def backtest_segment(strategy, candles: pd.DataFrame, start, end, costs, timeframe):
    # Warm-up history before the test window feeds indicators/features but never trades.
    window = candles[(candles["timestamp"] < end)]
    window = window[window["timestamp"] >= start - pd.Timedelta(seconds=TIMEFRAME_SECONDS[timeframe]) * (WARMUP_CANDLES + 5)]
    return await run_backtest(
        candles=to_candles(window), strategy=strategy, symbol="X", allocated_capital=CAPITAL,
        stop_loss_pct=STOP_LOSS_PCT, take_profit_pct=TAKE_PROFIT_PCT, costs=costs,
        trade_start=start.to_pydatetime(), timeframe_seconds=TIMEFRAME_SECONDS[timeframe],
    )


def summarize(metrics) -> dict:
    trades = metrics.trades
    return {
        "return_pct": metrics.total_return_pct,
        "max_drawdown_pct": metrics.max_drawdown_pct,
        "sharpe": metrics.sharpe_ratio,
        "profit_factor": metrics.profit_factor,
        "win_rate": metrics.win_rate,
        "trades": metrics.total_trades,
        "avg_trade_pct": metrics.expectancy_pct,
        "exposure_pct": metrics.exposure_pct,
        "fees": metrics.fees_paid,
        "traded_volume": round(sum(t.cost + t.quantity * t.exit_price for t in trades), 2),
        "buy_and_hold_pct": metrics.buy_and_hold_return_pct,
        "_pnls": [t.pnl for t in trades],
    }


async def evaluate(symbols, timeframe, root: Path, spec: LabelSpec, costs: BacktestCosts,
                   train_months=12, val_months=3, test_months=3) -> dict:
    datasets, provenance = [], {}
    for symbol in symbols:
        candles, quality, digest = load_dataset(dataset_path(root, symbol, timeframe), timeframe)
        datasets.append(build_symbol_data(symbol, candles, spec, timeframe))
        provenance[symbol] = {"sha256": digest, "quality": quality.as_dict(),
                              "first": str(candles["timestamp"].iloc[0]), "last": str(candles["timestamp"].iloc[-1])}
    rows = pooled(datasets)
    purge = pd.Timedelta(seconds=TIMEFRAME_SECONDS[timeframe] * spec.horizon)
    months = month_starts(rows["timestamp"].min(), rows["timestamp"].max())

    folds = []
    i = 0
    while i + train_months + val_months + test_months < len(months):
        t0, v0 = months[i], months[i + train_months]
        s0, s1 = months[i + train_months + val_months], months[i + train_months + val_months + test_months]
        train = between(rows, t0, v0, purge)
        val = between(rows, v0, s0, purge)
        tx, ty = matrix(train)
        vx, vy = matrix(val)
        selection = select_model(tx, ty, vx, vy, val["net_return"].to_numpy(), {
            "timeframe": timeframe, "label_spec": spec.as_dict(), "symbols": symbols,
            "training": {"train": [str(t0), str(v0)], "validation": [str(v0), str(s0)]},
        })
        fold = {"train": [str(t0), str(v0)], "validation": [str(v0), str(s0)],
                "test": [str(s0), str(s1)], "selected": selection.kind,
                "selection_reason": selection.reason, "validation_report": selection.validation,
                "symbols": {}}

        predictor = (ModelPredictor(selection.document, FEATURE_SCHEMA_VERSION, FEATURE_NAMES)
                     if selection.document else None)
        test_rows = between(rows, s0, s1)
        if predictor is not None:
            fold["decision"] = selection.document["decision"]
            x_test, y_test = matrix(test_rows)
            fold["test_classification"] = classification_metrics(
                y_test, predictor.predict_many(x_test), float(ty.mean()))

        for data in datasets:
            ml = MLSignalStrategy(predictor, timeframe,
                                  unavailable_reason=selection.reason)
            ml_metrics = await backtest_segment(ml, data.candles, s0, s1, costs, timeframe)
            rsi_metrics = await backtest_segment(SimpleRsiStrategy(), data.candles, s0, s1, costs, timeframe)
            segment = data.candles[(data.candles["timestamp"] >= s0) & (data.candles["timestamp"] < s1)]
            hourly_vol = float(np.log(segment["close"]).diff().std())
            bh = ml_metrics.buy_and_hold_return_pct
            fold["symbols"][data.symbol] = {
                "regime": regime(bh), "hourly_volatility": hourly_vol,
                "ml": summarize(ml_metrics), "rsi": summarize(rsi_metrics),
                "buy_and_hold_pct": bh, "no_trade_pct": 0.0,
            }
        folds.append(fold)
        i += test_months

    return {"generated_at": datetime.now(timezone.utc).isoformat(), "symbols": symbols,
            "timeframe": timeframe, "label_spec": spec.as_dict(), "costs": asdict(costs),
            "stop_loss_pct": STOP_LOSS_PCT, "take_profit_pct": TAKE_PROFIT_PCT,
            "data": provenance, "folds": folds, "aggregate": aggregate(folds)}


def aggregate(folds: list[dict]) -> dict:
    vols = [s["hourly_volatility"] for f in folds for s in f["symbols"].values()]
    vol_median = statistics.median(vols) if vols else 0
    out = {}
    for name in ("ml", "rsi", "buy_and_hold", "no_trade"):
        returns, dds, sharpes, pnls, trades, exposure, fees, by_regime = [], [], [], [], 0, [], 0.0, {}
        period_returns = []
        for fold in folds:
            fold_returns = []
            for s in fold["symbols"].values():
                if name in ("ml", "rsi"):
                    r = s[name]
                    ret = r["return_pct"]
                    dds.append(r["max_drawdown_pct"])
                    if r["sharpe"] is not None:
                        sharpes.append(r["sharpe"])
                    pnls += r["_pnls"]
                    trades += r["trades"]
                    exposure.append(r["exposure_pct"])
                    fees += r["fees"]
                else:
                    ret = s["buy_and_hold_pct"] if name == "buy_and_hold" else 0.0
                returns.append(ret)
                fold_returns.append(ret)
                key = f"{s['regime']}/{'high_vol' if s['hourly_volatility'] > vol_median else 'low_vol'}"
                by_regime.setdefault(key, []).append(ret)
            if fold_returns:
                # Symbols in one fold run side by side, not one after another.
                period_returns.append(statistics.mean(fold_returns))
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        # Capital split equally across symbols each test period, compounded over periods.
        compounded = (float(np.prod([1 + r / 100 for r in period_returns]) - 1) * 100
                      if period_returns else None)
        out[name] = {
            "windows": len(returns),
            "test_periods": len(period_returns),
            "mean_window_return_pct": statistics.mean(returns) if returns else None,
            "median_window_return_pct": statistics.median(returns) if returns else None,
            "stdev_window_return_pct": statistics.stdev(returns) if len(returns) > 1 else None,
            "compounded_return_pct_equal_split": compounded,
            "positive_windows": sum(r > 0 for r in returns),
            "worst_window_drawdown_pct": min(dds) if dds else None,
            "mean_sharpe": statistics.mean(sharpes) if sharpes else None,
            "trades": trades if name in ("ml", "rsi") else None,
            "pooled_profit_factor": (sum(wins) / -sum(losses)) if losses and sum(losses) < 0 else None,
            "pooled_win_rate": (len(wins) / len(pnls)) if pnls else None,
            "mean_pnl_per_trade": (sum(pnls) / len(pnls)) if pnls else None,
            "mean_exposure_pct": statistics.mean(exposure) if exposure else None,
            "fees": fees if name in ("ml", "rsi") else None,
            "by_regime_mean_return_pct": {k: statistics.mean(v) for k, v in sorted(by_regime.items())},
        }
    return out


def markdown(report: dict) -> str:
    agg = report["aggregate"]
    lines = [
        f"# Walk-forward report ({report['timeframe']}, {', '.join(report['symbols'])})",
        f"Generated {report['generated_at']}. Costs: {report['costs']}. "
        f"SL {report['stop_loss_pct']}% / TP {report['take_profit_pct']}%. Label: {report['label_spec']}.",
        "", "## Aggregate over out-of-sample test windows", "",
        "| Strategy | Windows | Mean ret % | Median % | Stdev % | Compounded % | Positive | Worst DD % | Mean Sharpe | Trades | PF | Win rate | PnL/trade | Exposure % | Fees |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    def fmt(v, d=2):
        return "–" if v is None else (f"{v:.{d}f}" if isinstance(v, float) else str(v))

    for name, a in agg.items():
        lines.append(
            f"| {name} | {a['windows']} | {fmt(a['mean_window_return_pct'])} | {fmt(a['median_window_return_pct'])} | "
            f"{fmt(a['stdev_window_return_pct'])} | {fmt(a['compounded_return_pct_equal_split'])} | "
            f"{a['positive_windows']}/{a['windows']} | {fmt(a['worst_window_drawdown_pct'])} | "
            f"{fmt(a['mean_sharpe'])} | {fmt(a['trades'])} | {fmt(a['pooled_profit_factor'])} | "
            f"{fmt(a['pooled_win_rate'])} | {fmt(a['mean_pnl_per_trade'])} | {fmt(a['mean_exposure_pct'])} | {fmt(a['fees'])} |")
    lines += ["", "## By regime (mean window return %)", "",
              "| Strategy | " + " | ".join(sorted(agg["ml"]["by_regime_mean_return_pct"])) + " |",
              "|---|" + "---|" * len(agg["ml"]["by_regime_mean_return_pct"])]
    for name, a in agg.items():
        lines.append(f"| {name} | " + " | ".join(fmt(v) for _, v in sorted(a["by_regime_mean_return_pct"].items())) + " |")
    lines += ["", "## Per window", "",
              "| Test window | Model | Buy thr | Test AUC | Test logloss / base | Symbol | Regime | ML % (trades) | RSI % (trades) | B&H % |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for f in report["folds"]:
        tc = f.get("test_classification") or {}
        for sym, s in f["symbols"].items():
            lines.append(
                f"| {f['test'][0][:10]}->{f['test'][1][:10]} | {f['selected'] or 'none'} | "
                f"{fmt((f.get('decision') or {}).get('buy_threshold'))} | {fmt(tc.get('auc'), 3)} | "
                f"{fmt(tc.get('log_loss'), 4)} / {fmt(tc.get('base_rate_log_loss'), 4)} | {sym} | {s['regime']} | "
                f"{fmt(s['ml']['return_pct'])} ({s['ml']['trades']}) | {fmt(s['rsi']['return_pct'])} ({s['rsi']['trades']}) | "
                f"{fmt(s['buy_and_hold_pct'])} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", action="append", required=True)
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--root", type=Path, default=Path("data/ml/ohlcv"))
    parser.add_argument("--out", type=Path, default=Path("artifacts/reports/walk_forward"))
    parser.add_argument("--horizon", type=int, default=12)
    parser.add_argument("--fee", type=float, default=0.001)
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    args = parser.parse_args()

    spec = LabelSpec(horizon=args.horizon, taker_fee_rate=args.fee, slippage_bps=args.slippage_bps)
    costs = BacktestCosts(taker_fee_rate=args.fee, slippage_bps=args.slippage_bps)
    report = asyncio.run(evaluate(args.symbol, args.timeframe, args.root, spec, costs))
    args.out.mkdir(parents=True, exist_ok=True)
    for fold in report["folds"]:
        for s in fold["symbols"].values():
            for name in ("ml", "rsi"):
                s[name].pop("_pnls", None)
    (args.out / "report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    (args.out / "report.md").write_text(markdown(report), encoding="utf-8")
    print(markdown(report))


if __name__ == "__main__":
    main()
