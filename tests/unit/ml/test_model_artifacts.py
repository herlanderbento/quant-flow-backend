import copy
import json

import numpy as np
import pytest
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from ml.models.artifact import (
    ARTIFACT_FORMAT,
    ArtifactError,
    ModelPredictor,
    read_artifact,
    write_artifact,
)
from ml.models.export import (
    gradient_boosting_params,
    logistic_regression_params,
    random_forest_params,
)

FEATURES = ["a", "b", "c", "d"]
SCHEMA = "test-v1"


def data(n=600, seed=3):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, len(FEATURES))) * [1, 5, 0.01, 100]
    logits = 0.8 * x[:, 0] - 0.1 * x[:, 1] + 40 * x[:, 2]
    y = (rng.uniform(size=n) < 1 / (1 + np.exp(-logits))).astype(int)
    return x, y


def document(kind, params):
    return {
        "format": ARTIFACT_FORMAT, "kind": kind, "model_version": "t1",
        "feature_schema_version": SCHEMA, "feature_names": FEATURES,
        "params": params, "decision": {"buy_threshold": 0.6, "sell_threshold": 0.4},
    }


def roundtrip(tmp_path, kind, params) -> ModelPredictor:
    path = tmp_path / f"{kind}.json"
    write_artifact(document(kind, params), path)
    return ModelPredictor.load(path, SCHEMA, FEATURES)


def test_logistic_regression_matches_sklearn(tmp_path):
    x, y = data()
    scaler = StandardScaler().fit(x)
    model = LogisticRegression(max_iter=1000).fit(scaler.transform(x), y)
    predictor = roundtrip(tmp_path, "logistic_regression", logistic_regression_params(scaler, model))
    expected = model.predict_proba(scaler.transform(x))[:, 1]
    np.testing.assert_allclose(predictor.predict_many(x), expected, rtol=1e-10, atol=1e-12)


def test_random_forest_matches_sklearn(tmp_path):
    x, y = data()
    model = RandomForestClassifier(n_estimators=25, max_depth=6, min_samples_leaf=5,
                                   random_state=0).fit(x, y)
    predictor = roundtrip(tmp_path, "random_forest", random_forest_params(model))
    np.testing.assert_allclose(predictor.predict_many(x), model.predict_proba(x)[:, 1], atol=1e-12)


def test_gradient_boosting_matches_sklearn(tmp_path):
    x, y = data()
    model = GradientBoostingClassifier(n_estimators=40, max_depth=3, learning_rate=0.05,
                                       random_state=0).fit(x, y)
    predictor = roundtrip(tmp_path, "gradient_boosting", gradient_boosting_params(model, x))
    np.testing.assert_allclose(predictor.predict_many(x), model.predict_proba(x)[:, 1], atol=1e-10)


def _lr_artifact(tmp_path):
    x, y = data()
    scaler = StandardScaler().fit(x)
    model = LogisticRegression(max_iter=1000).fit(scaler.transform(x), y)
    path = tmp_path / "lr.json"
    write_artifact(document("logistic_regression", logistic_regression_params(scaler, model)), path)
    return path


def test_tampered_artifact_is_rejected(tmp_path):
    path = _lr_artifact(tmp_path)
    doc = read_artifact(path)
    doc["decision"]["buy_threshold"] = 0.51  # edited without updating the checksum
    with pytest.raises(ArtifactError, match="checksum"):
        ModelPredictor(doc, SCHEMA, FEATURES)


def test_incompatible_feature_schema_is_rejected(tmp_path):
    path = _lr_artifact(tmp_path)
    with pytest.raises(ArtifactError, match="schema"):
        ModelPredictor.load(path, "v2", FEATURES)
    with pytest.raises(ArtifactError, match="feature names"):
        ModelPredictor.load(path, SCHEMA, list(reversed(FEATURES)))


def test_cyclic_tree_is_rejected(tmp_path):
    tree = {"left": [1, 0, -1], "right": [2, -1, -1], "feature": [0, 0, 0],
            "threshold": [0.0, 0.0, 0.0], "value": [0.5, 0.5, 0.5]}
    doc = document("random_forest", {"trees": [tree]})
    path = tmp_path / "bad.json"
    write_artifact(doc, path)
    with pytest.raises(ArtifactError):
        ModelPredictor.load(path, SCHEMA, FEATURES)


def test_non_finite_numbers_and_invalid_thresholds_are_rejected(tmp_path):
    path = tmp_path / "nan.json"
    path.write_text(json.dumps({"format": ARTIFACT_FORMAT, "x": float("nan")}), encoding="utf-8")
    with pytest.raises(ArtifactError, match="non-finite"):
        read_artifact(path)

    doc = read_artifact(_lr_artifact(tmp_path))
    doc = copy.deepcopy(doc)
    doc["decision"] = {"buy_threshold": 0.3, "sell_threshold": 0.6}
    path2 = tmp_path / "thr.json"
    write_artifact(doc, path2)
    with pytest.raises(ArtifactError, match="thresholds"):
        ModelPredictor.load(path2, SCHEMA, FEATURES)


def test_prediction_refuses_missing_or_non_finite_features(tmp_path):
    predictor = ModelPredictor.load(_lr_artifact(tmp_path), SCHEMA, FEATURES)
    with pytest.raises(ArtifactError):
        predictor.predict_proba({"a": 1.0, "b": 2.0, "c": 3.0})
    with pytest.raises(ArtifactError):
        predictor.predict_proba({"a": 1.0, "b": float("nan"), "c": 0.0, "d": 0.0})
