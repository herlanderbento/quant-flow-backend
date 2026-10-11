"""
Model artifacts as plain JSON plus a pure-numpy predictor.

Artifacts are data, never code: no pickle/joblib is ever loaded. The loader validates
structure, types, sizes, the feature schema and a SHA-256 of the canonical payload.
"""
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ARTIFACT_FORMAT = "quantflow-model/1"
SUPPORTED_KINDS = ("logistic_regression", "random_forest", "gradient_boosting")
MAX_ARTIFACT_BYTES = 50 * 1024 * 1024
MAX_TREES = 2000
MAX_NODES_PER_TREE = 200_000


class ArtifactError(ValueError):
    """The artifact is malformed, tampered with, or incompatible with this code."""


def canonical_sha256(payload: dict) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def write_artifact(payload: dict, path: Path) -> str:
    payload = {k: v for k, v in payload.items() if k != "sha256"}
    digest = canonical_sha256(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({**payload, "sha256": digest}, handle, sort_keys=True, allow_nan=False)
    return digest


def read_artifact(path: Path) -> dict:
    size = Path(path).stat().st_size
    if size > MAX_ARTIFACT_BYTES:
        raise ArtifactError(f"artifact too large ({size} bytes)")
    with open(path, "r", encoding="utf-8") as handle:
        try:
            document = json.load(handle, parse_constant=_reject_constant)
        except json.JSONDecodeError as error:
            raise ArtifactError(f"artifact is not valid JSON: {error}") from error
    return document


def _reject_constant(name):
    raise ArtifactError(f"non-finite number {name} in artifact")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ArtifactError(message)


def _float_list(values, name: str, length: int | None = None) -> np.ndarray:
    _require(isinstance(values, list), f"{name} must be a list")
    _require(length is None or len(values) == length, f"{name} has wrong length")
    _require(all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values),
             f"{name} must contain numbers")
    array = np.asarray(values, dtype=np.float64)
    _require(bool(np.isfinite(array).all()), f"{name} contains non-finite numbers")
    return array


def _int_list(values, name: str, length: int) -> np.ndarray:
    _require(isinstance(values, list) and len(values) == length, f"{name} has wrong length")
    _require(all(isinstance(v, int) and not isinstance(v, bool) for v in values),
             f"{name} must contain integers")
    return np.asarray(values, dtype=np.int64)


@dataclass(frozen=True)
class _Tree:
    left: np.ndarray
    right: np.ndarray
    feature: np.ndarray
    threshold: np.ndarray
    value: np.ndarray  # leaf output (probability of class 1, or regression value)

    def predict(self, x32: np.ndarray) -> float:
        node = 0
        while self.left[node] != -1:
            # sklearn trees compare float32 inputs against float64 thresholds.
            if float(x32[self.feature[node]]) <= self.threshold[node]:
                node = self.left[node]
            else:
                node = self.right[node]
        return float(self.value[node])


def _parse_tree(raw: dict, n_features: int) -> _Tree:
    _require(isinstance(raw, dict), "tree must be an object")
    n = len(raw.get("left", []))
    _require(0 < n <= MAX_NODES_PER_TREE, "tree size out of bounds")
    left = _int_list(raw["left"], "left", n)
    right = _int_list(raw["right"], "right", n)
    feature = _int_list(raw["feature"], "feature", n)
    threshold = _float_list(raw["threshold"], "threshold", n)
    value = _float_list(raw["value"], "value", n)
    leaves = left == -1
    _require(bool(((right == -1) == leaves).all()), "inconsistent leaves")
    internal = ~leaves
    _require(bool(((left[internal] > np.flatnonzero(internal)) & (left[internal] < n)).all()),
             "child index out of bounds")
    _require(bool(((right[internal] > np.flatnonzero(internal)) & (right[internal] < n)).all()),
             "child index out of bounds")
    _require(bool(((feature[internal] >= 0) & (feature[internal] < n_features)).all()),
             "feature index out of bounds")
    return _Tree(left, right, feature, threshold, value)


class ModelPredictor:
    """Validated, read-only model: probability that the next trade is favourable."""

    def __init__(self, document: dict, expected_schema_version: str, expected_features: list[str]):
        _require(isinstance(document, dict), "artifact must be an object")
        _require(document.get("format") == ARTIFACT_FORMAT, "unsupported artifact format")
        claimed = document.get("sha256")
        payload = {k: v for k, v in document.items() if k != "sha256"}
        _require(isinstance(claimed, str) and claimed == canonical_sha256(payload),
                 "artifact checksum mismatch")
        _require(document.get("feature_schema_version") == expected_schema_version,
                 "feature schema version mismatch")
        _require(document.get("feature_names") == expected_features, "feature names mismatch")
        kind = document.get("kind")
        _require(kind in SUPPORTED_KINDS, f"unsupported model kind {kind!r}")

        self.document = document
        self.kind = kind
        self.model_version = str(document.get("model_version"))
        approval = document.get("approval") or {}
        # Only a human decision recorded inside the checksummed artifact lets a model trade.
        self.validation_failed = document.get("validation_failed")
        self.approved_for_trading = (
            not self.validation_failed
            and isinstance(approval, dict) and approval.get("approved_for_trading") is True
            and bool(approval.get("approved_by")) and bool(approval.get("reason"))
        )
        self.feature_names = list(expected_features)
        n = len(expected_features)
        params = document.get("params")
        _require(isinstance(params, dict), "params must be an object")

        decision = document.get("decision", {})
        self.buy_threshold = float(_float_list([decision.get("buy_threshold")], "buy_threshold")[0])
        self.sell_threshold = float(_float_list([decision.get("sell_threshold")], "sell_threshold")[0])
        _require(0 < self.sell_threshold < self.buy_threshold < 1, "invalid decision thresholds")

        if kind == "logistic_regression":
            self.mean = _float_list(params.get("mean"), "mean", n)
            self.scale = _float_list(params.get("scale"), "scale", n)
            _require(bool((self.scale > 0).all()), "scale must be positive")
            self.coef = _float_list(params.get("coef"), "coef", n)
            self.intercept = float(_float_list([params.get("intercept")], "intercept")[0])
        else:
            trees = params.get("trees")
            _require(isinstance(trees, list) and 0 < len(trees) <= MAX_TREES, "invalid tree list")
            self.trees = [_parse_tree(tree, n) for tree in trees]
            if kind == "gradient_boosting":
                self.init_raw = float(_float_list([params.get("init_raw")], "init_raw")[0])
                self.learning_rate = float(
                    _float_list([params.get("learning_rate")], "learning_rate")[0])

    @classmethod
    def load(cls, path: Path, expected_schema_version: str,
             expected_features: list[str]) -> "ModelPredictor":
        return cls(read_artifact(path), expected_schema_version, expected_features)

    def predict_proba(self, features: dict[str, float]) -> float:
        _require(set(features) == set(self.feature_names), "feature set mismatch")
        x = np.asarray([features[name] for name in self.feature_names], dtype=np.float64)
        if not np.isfinite(x).all():
            raise ArtifactError("non-finite feature value")
        if self.kind == "logistic_regression":
            z = float(np.dot((x - self.mean) / self.scale, self.coef) + self.intercept)
            return _sigmoid(z)
        x32 = x.astype(np.float32)
        if self.kind == "random_forest":
            return float(np.mean([tree.predict(x32) for tree in self.trees]))
        raw = self.init_raw + self.learning_rate * sum(tree.predict(x32) for tree in self.trees)
        return _sigmoid(raw)

    def predict_many(self, matrix: np.ndarray) -> np.ndarray:
        return np.asarray([
            self.predict_proba(dict(zip(self.feature_names, row))) for row in matrix
        ])


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)
