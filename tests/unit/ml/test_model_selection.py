import numpy as np

from ml.features.pipeline import FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from ml.models.artifact import ModelPredictor
from ml.training.candidates import choose_threshold, select_model

N_FEATURES = len(FEATURE_NAMES)


def split(n, signal_strength, seed):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, N_FEATURES))
    logits = signal_strength * x[:, 0]
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-logits))).astype(int)
    net = np.where(y == 1, 0.004, -0.004) + rng.normal(0, 0.001, n)
    return x, y, net


def test_learnable_signal_produces_an_unapproved_artifact():
    tx, ty, _ = split(3000, 2.0, 1)
    vx, vy, vnet = split(1500, 2.0, 2)
    selection = select_model(tx, ty, vx, vy, vnet, {})
    assert selection.document is not None
    predictor = ModelPredictor(selection.document, FEATURE_SCHEMA_VERSION, FEATURE_NAMES)
    assert predictor.approved_for_trading is False  # needs an explicit human approval
    assert predictor.validation_failed is None
    assert 0.5 <= predictor.buy_threshold <= 0.8


def test_pure_noise_produces_no_model():
    tx, ty, _ = split(3000, 0.0, 3)
    vx, vy, vnet = split(1500, 0.0, 4)
    selection = select_model(tx, ty, vx, vy, vnet, {})
    assert selection.document is None
    assert selection.reason


def test_research_artifact_is_marked_and_can_never_trade():
    tx, ty, _ = split(3000, 0.0, 5)
    vx, vy, vnet = split(1500, 0.0, 6)
    selection = select_model(tx, ty, vx, vy, vnet, {}, research_shadow_only=True)
    document = selection.document
    document["approval"] = {"approved_for_trading": True, "approved_by": "x", "reason": "y"}
    from ml.models.artifact import canonical_sha256
    document["sha256"] = canonical_sha256({k: v for k, v in document.items() if k != "sha256"})
    predictor = ModelPredictor(document, FEATURE_SCHEMA_VERSION, FEATURE_NAMES)
    assert predictor.validation_failed
    assert predictor.approved_for_trading is False


def test_threshold_requires_enough_signals_and_positive_mean():
    p = np.linspace(0, 1, 1000)
    assert choose_threshold(p, np.full(1000, -0.01))[0] is None
    net = np.where(p > 0.7, 0.01, -0.01)
    threshold, report = choose_threshold(p, net)
    assert threshold is not None and threshold >= 0.7
    assert all(row["signals"] >= 30 for row in report["candidates"])
