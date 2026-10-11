from datetime import timedelta

import pandas as pd
import pytest

from ml.evaluation.shadow_report import score
from ml.labels import LabelSpec, net_forward_returns
from tests.unit.ml.test_features_and_labels import random_walk


def test_predictions_are_scored_against_the_realized_label_and_pending_ones_reported():
    candles = random_walk(300)
    spec = LabelSpec(horizon=12)
    net = net_forward_returns(candles, spec, "1h")
    close_of = lambda i: candles["timestamp"].iloc[i] + timedelta(hours=1)  # noqa: E731
    predictions = pd.DataFrame([
        {"symbol": "BTC/USDT", "mode": "shadow", "ai_model_version": "v", "probability": 0.7,
         "decision": "BUY", "strategy_signal": "HOLD", "reason": None, "feature_candle_close": close_of(100)},
        {"symbol": "BTC/USDT", "mode": "shadow", "ai_model_version": "v", "probability": 0.3,
         "decision": "SELL", "strategy_signal": "HOLD", "reason": None, "feature_candle_close": close_of(150)},
        {"symbol": "BTC/USDT", "mode": "shadow", "ai_model_version": "v", "probability": 0.6,
         "decision": "BUY", "strategy_signal": "BUY", "reason": None, "feature_candle_close": close_of(295)},
        {"symbol": "BTC/USDT", "mode": "shadow", "ai_model_version": "v", "probability": None,
         "decision": "HOLD", "strategy_signal": "HOLD", "reason": "rejected: stale", "feature_candle_close": None},
    ])
    report = score(predictions, {"BTC/USDT": candles}, spec, "1h")

    assert report["predictions"] == 4
    assert report["rejected"] == 1
    assert report["rejection_reasons"] == {"rejected: stale": 1}
    assert report["scored"] == 2
    assert report["pending"] == 2  # horizon not elapsed (295) + rejected
    assert report["mean_net_return_model_buy"] == pytest.approx(net.iloc[100])
    assert report["model_buy_signals"] == 1
