"""Fit candidate models, pick one on validation data, pick the decision threshold."""
from dataclasses import dataclass

import numpy as np
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

from ml.features.pipeline import FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from ml.models.artifact import ARTIFACT_FORMAT, ModelPredictor, canonical_sha256
from ml.models.export import (
    gradient_boosting_params,
    logistic_regression_params,
    random_forest_params,
)

RANDOM_STATE = 42
MIN_SIGNALS_FOR_THRESHOLD = 30
EXIT_MARGIN = 0.02
RESEARCH_DEFAULT_BUY_THRESHOLD = 0.6


def fit_candidate(kind: str, x: np.ndarray, y: np.ndarray) -> dict:
    """Returns artifact `params` for the fitted model (sklearn objects are discarded)."""
    if kind == "logistic_regression":
        scaler = StandardScaler().fit(x)
        model = LogisticRegression(C=0.1, max_iter=2000).fit(scaler.transform(x), y)
        return logistic_regression_params(scaler, model)
    if kind == "random_forest":
        model = RandomForestClassifier(
            n_estimators=200, max_depth=6, min_samples_leaf=50, max_features="sqrt",
            n_jobs=-1, random_state=RANDOM_STATE,
        ).fit(x, y)
        return random_forest_params(model)
    if kind == "gradient_boosting":
        model = GradientBoostingClassifier(
            n_estimators=150, max_depth=3, learning_rate=0.05, subsample=0.8,
            min_samples_leaf=50, random_state=RANDOM_STATE,
        ).fit(x, y)
        return gradient_boosting_params(model, x)
    raise ValueError(kind)


CANDIDATE_KINDS = ("logistic_regression", "random_forest", "gradient_boosting")


def build_document(kind: str, params: dict, buy: float, sell: float, extra: dict) -> dict:
    document = {
        "format": ARTIFACT_FORMAT,
        "kind": kind,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": FEATURE_NAMES,
        "params": params,
        "decision": {"buy_threshold": buy, "sell_threshold": sell},
        **extra,
    }
    document["model_version"] = f"{kind}-{canonical_sha256(document)[:12]}"
    document["sha256"] = canonical_sha256(document)
    return document


def classification_metrics(y: np.ndarray, p: np.ndarray, base_rate: float) -> dict:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    base = np.full_like(p, np.clip(base_rate, 1e-6, 1 - 1e-6))
    bins = np.linspace(0, 1, 6)
    calibration = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (p >= lo) & (p < hi if hi < 1 else p <= hi)
        if mask.sum():
            calibration.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(mask.sum()),
                                "mean_p": float(p[mask].mean()), "observed": float(y[mask].mean())})
    return {
        "n": int(len(y)),
        "positive_rate": float(y.mean()),
        "auc": float(roc_auc_score(y, p)) if len(set(y)) > 1 else None,
        "log_loss": float(log_loss(y, p, labels=[0, 1])),
        "base_rate_log_loss": float(log_loss(y, base, labels=[0, 1])),
        "brier": float(brier_score_loss(y, p)),
        "base_rate_brier": float(brier_score_loss(y, base)),
        "calibration": calibration,
    }


def choose_threshold(p: np.ndarray, net_returns: np.ndarray) -> tuple[float | None, dict]:
    """Highest mean net return among candidate thresholds with enough signals; None if <= 0."""
    best, best_mean, table = None, 0.0, []
    for threshold in np.round(np.linspace(0.50, 0.80, 31), 2):
        selected = net_returns[p >= threshold]
        if len(selected) < MIN_SIGNALS_FOR_THRESHOLD:
            continue
        mean = float(selected.mean())
        table.append({"threshold": float(threshold), "signals": int(len(selected)), "mean_net_return": mean})
        if mean > best_mean:
            best, best_mean = float(threshold), mean
    return best, {"candidates": table, "chosen_mean_net_return": best_mean if best else None}


@dataclass
class Selection:
    kind: str | None
    document: dict | None
    validation: dict  # per-candidate metrics and the threshold search
    reason: str | None = None


def select_model(train_x, train_y, val_x, val_y, val_net, extra: dict,
                 research_shadow_only: bool = False) -> Selection:
    base_rate = float(train_y.mean())
    report: dict = {"base_rate": base_rate, "candidates": {}}
    best_kind, best_loss, best_params, best_p = None, None, None, None
    for kind in CANDIDATE_KINDS:
        params = fit_candidate(kind, train_x, train_y)
        probe = ModelPredictor(build_document(kind, params, 0.6, 0.4, {}), FEATURE_SCHEMA_VERSION, FEATURE_NAMES)
        p = probe.predict_many(val_x)
        metrics = classification_metrics(val_y, p, base_rate)
        report["candidates"][kind] = metrics
        beats_base = metrics["log_loss"] < metrics["base_rate_log_loss"]
        if (beats_base or research_shadow_only) and (
            best_loss is None or metrics["log_loss"] < best_loss
        ):
            best_kind, best_loss, best_params, best_p = kind, metrics["log_loss"], params, p
            best_beats_base = beats_base

    if best_kind is None:
        return Selection(None, None, report, "no candidate beats the base-rate log loss on validation")

    failure = None if best_beats_base else "no candidate beats the base-rate log loss on validation"
    threshold, search = choose_threshold(best_p, val_net)
    report["threshold_search"] = search
    if threshold is None:
        failure = failure or "no threshold with positive validation net return"
        if not research_shadow_only:
            return Selection(None, None, report, failure)
        threshold = RESEARCH_DEFAULT_BUY_THRESHOLD
    if failure and not research_shadow_only:
        return Selection(None, None, report, failure)

    sell = round(min(0.5, threshold - EXIT_MARGIN), 4)
    extra = {**extra, "validation": {k: v for k, v in report.items()}}
    if failure:
        # Recorded inside the checksum: such an artifact can never be approved to trade.
        extra["validation_failed"] = failure
    document = build_document(best_kind, best_params, threshold, sell, extra)
    return Selection(best_kind, document, report, failure)
