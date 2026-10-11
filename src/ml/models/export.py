"""Convert fitted scikit-learn models into JSON artifact params (training-time only)."""
import numpy as np


def _tree_params(tree, leaf_value) -> dict:
    t = tree.tree_
    return {
        "left": [int(v) for v in t.children_left],
        "right": [int(v) for v in t.children_right],
        "feature": [int(max(v, 0)) for v in t.feature],
        "threshold": [float(v) for v in t.threshold],
        "value": [float(leaf_value(t.value[i])) for i in range(t.node_count)],
    }


def logistic_regression_params(scaler, model) -> dict:
    return {
        "mean": [float(v) for v in scaler.mean_],
        "scale": [float(v) for v in scaler.scale_],
        "coef": [float(v) for v in model.coef_[0]],
        "intercept": float(model.intercept_[0]),
    }


def random_forest_params(model) -> dict:
    positive = int(np.flatnonzero(model.classes_ == 1)[0])

    def probability_of_positive(node_value):
        counts = np.asarray(node_value[0], dtype=np.float64)
        total = counts.sum()
        return counts[positive] / total if total > 0 else 0.0

    return {"trees": [_tree_params(est, probability_of_positive) for est in model.estimators_]}


def gradient_boosting_params(model, sample: np.ndarray) -> dict:
    init_raw = float(model._raw_predict_init(sample[:1].astype(np.float32))[0, 0])
    return {
        "init_raw": init_raw,
        "learning_rate": float(model.learning_rate),
        "trees": [
            _tree_params(stage[0], lambda node_value: node_value[0][0])
            for stage in model.estimators_
        ],
    }
