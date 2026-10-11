"""
Score logged model predictions against what actually happened afterwards.

    python -m ml.evaluation.shadow_report --since 2026-10-10T00:00:00Z --out shadow.json

For each recorded prediction on closed candle t, the realized outcome is the same net
return the model was trained to predict (buy at open t+1, sell at close t+horizon, after
costs). Predictions whose horizon has not elapsed yet are reported as pending.
"""
import argparse
import asyncio
import json
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import select

import shared.infra.db.metadata  # noqa: F401  registers every ORM model
from ml.data.ohlcv import TIMEFRAME_SECONDS, normalize_ohlcv
from ml.labels import LabelSpec, net_forward_returns
from shared.infra.db.database import AsyncSessionLocal, engine
from trader.infra.db.sql_models import AIPredictionModel


def score(predictions: pd.DataFrame, candles_by_symbol: dict[str, pd.DataFrame],
          spec: LabelSpec, timeframe: str) -> dict:
    period = pd.Timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
    rows = []
    for symbol, group in predictions.groupby("symbol"):
        candles = candles_by_symbol.get(symbol)
        if candles is None or candles.empty:
            continue
        net = net_forward_returns(candles, spec, timeframe)
        realized = pd.Series(net.to_numpy(), index=candles["timestamp"] + period)  # keyed by close time
        for record in group.itertuples(index=False):
            value = realized.get(pd.Timestamp(record.feature_candle_close))
            rows.append({**record._asdict(), "net_return": None if value is None or pd.isna(value) else float(value)})
    scored = pd.DataFrame(rows)
    report: dict = {"predictions": int(len(predictions)),
                    "rejected": int(predictions["probability"].isna().sum()) if len(predictions) else 0,
                    "rejection_reasons": predictions["reason"].dropna().value_counts().to_dict() if len(predictions) else {}}
    if scored.empty:
        return {**report, "scored": 0, "pending": int(len(predictions))}
    done = scored.dropna(subset=["net_return", "probability"])
    report["pending"] = int(len(scored) - len(done))
    report["scored"] = int(len(done))
    if done.empty:
        return report

    y = (done["net_return"] > spec.min_edge).astype(int).to_numpy()
    p = done["probability"].astype(float).to_numpy()
    buys = done[done["decision"] == "BUY"]
    report.update({
        "base_rate": float(y.mean()),
        "mean_net_return_all": float(done["net_return"].mean()),
        "model_buy_signals": int(len(buys)),
        "mean_net_return_model_buy": float(buys["net_return"].mean()) if len(buys) else None,
        "hit_rate_model_buy": float((buys["net_return"] > spec.min_edge).mean()) if len(buys) else None,
        "strategy_buy_signals": int((done["strategy_signal"] == "BUY").sum()),
        "mean_net_return_strategy_buy": (float(done.loc[done["strategy_signal"] == "BUY", "net_return"].mean())
                                         if (done["strategy_signal"] == "BUY").any() else None),
        "brier": float(np.mean((p - y) ** 2)),
        "base_rate_brier": float(np.mean((y.mean() - y) ** 2)),
        "agreement_with_strategy": float((done["decision"] == done["strategy_signal"]).mean()),
        "model_versions": done["ai_model_version"].value_counts().to_dict(),
    })
    if len(set(y)) > 1:
        from sklearn.metrics import roc_auc_score  # optional: research dependency
        report["auc"] = float(roc_auc_score(y, p))
    return report


async def load_predictions(since: datetime) -> pd.DataFrame:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(AIPredictionModel).where(AIPredictionModel.created_at >= since))
        models = result.scalars().all()
    await engine.dispose()
    return pd.DataFrame([{
        "symbol": m.symbol, "mode": m.mode, "ai_model_version": m.ai_model_version,
        "probability": float(m.probability) if m.probability is not None else None,
        "decision": m.decision, "strategy_signal": m.strategy_signal, "reason": m.reason,
        "feature_candle_close": m.feature_candle_close,
    } for m in models])


async def fetch_candles(symbols, timeframe, since_ms) -> dict[str, pd.DataFrame]:
    from trader.infra.gateway.bybit_gateway import BybitGateway  # public endpoints only
    gateway = BybitGateway(api_key="", api_secret="", is_testnet=False)
    out = {}
    try:
        now_ms = int(time.time() * 1000)
        for symbol in symbols:
            rows = await gateway.fetch_ohlcv_history(symbol, timeframe, since_ms, now_ms)
            period_ms = TIMEFRAME_SECONDS[timeframe] * 1000
            out[symbol], _ = normalize_ohlcv([r for r in rows if r[0] + period_ms <= now_ms], timeframe)
    finally:
        await gateway.close()
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", required=True)
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    predictions = asyncio.run(load_predictions(since))
    if predictions.empty:
        print("No predictions recorded since", since)
        return
    since_ms = int((since.timestamp() - 3 * 86400) * 1000)
    candles = asyncio.run(fetch_candles(sorted(predictions["symbol"].unique()), args.timeframe, since_ms))
    report = {"generated_at": datetime.now(timezone.utc).isoformat(), "since": since.isoformat(),
              **score(predictions, candles, LabelSpec(), args.timeframe)}
    text = json.dumps(report, indent=2, default=str)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            handle.write(text)


if __name__ == "__main__":
    main()
