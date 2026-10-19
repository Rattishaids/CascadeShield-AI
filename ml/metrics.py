"""Prediction metrics, transparent undefined cases and simulation-domain calibration."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (average_precision_score, brier_score_loss, confusion_matrix,
                             f1_score, precision_score, recall_score, roc_auc_score)
from sklearn.linear_model import LogisticRegression


def regression(y, p) -> dict:
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    if not len(y) or len(y) != len(p) or not np.isfinite(y).all() or not np.isfinite(p).all():
        raise ValueError("Finite nonempty matched regression observations are required")
    error = p - y
    return {"n": len(y), "mae": float(np.abs(error).mean()),
            "rmse": float(np.sqrt(np.square(error).mean())), "bias": float(error.mean())}


def classification(y, p) -> dict:
    y, p = np.asarray(y, dtype=int), np.asarray(p, dtype=float)
    if not len(y) or len(y) != len(p) or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any() or not set(y) <= {0, 1}:
        raise ValueError("Binary matched labels and finite probabilities in [0,1] are required")
    decision = p >= .5
    both = len(np.unique(y)) == 2
    bins = []
    for lower in np.arange(0, 1, .1):
        mask = (p >= lower) & ((p < lower + .1) if lower < .899 else (p <= 1))
        if mask.any():
            bins.append({"lower": float(lower), "n": int(mask.sum()), "predicted": float(p[mask].mean()),
                         "observed": float(y[mask].mean())})
    return {"n": len(y), "positive": int(y.sum()), "negative": int((1-y).sum()),
            "precision": float(precision_score(y, decision, zero_division=0)),
            "recall": float(recall_score(y, decision, zero_division=0)),
            "f1": float(f1_score(y, decision, zero_division=0)),
            "prAuc": float(average_precision_score(y, p)) if both else None,
            "rocAuc": float(roc_auc_score(y, p)) if both else None,
            "brier": float(brier_score_loss(y, p)), "confusionMatrix": confusion_matrix(y, decision, labels=[0, 1]).tolist(),
            "calibrationBins": bins, "aucUndefinedReason": None if both else "Only one target class is present"}


def logit(p):
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1-1e-6)
    return np.log(p / (1-p))


def fit_calibration(y, p) -> dict:
    y, p = np.asarray(y, dtype=int), np.asarray(p, dtype=float)
    if len(y) < 8 or len(np.unique(y)) < 2:
        return {"status": "UNAVAILABLE_SINGLE_CLASS_OR_SMALL_CALIBRATION_SET", "coefficient": 1., "intercept": 0.,
                "n": len(y), "domain": "SIMULATED_PARAMETERIZED_CHENNAI_OPERATIONS"}
    fit = LogisticRegression(C=1., solver="lbfgs", random_state=4001).fit(logit(p).reshape(-1, 1), y)
    return {"status": "PLATT_CALIBRATED_ON_SEPARATE_SIMULATED_SCENARIOS", "coefficient": float(fit.coef_[0, 0]),
            "intercept": float(fit.intercept_[0]), "n": len(y),
            "domain": "SIMULATED_PARAMETERIZED_CHENNAI_OPERATIONS"}


def calibrated(p, config):
    z = np.clip(config["coefficient"] * logit(p) + config["intercept"], -40, 40)
    return 1 / (1 + np.exp(-z))


def interval_radius(y, p) -> dict:
    errors = np.abs(np.asarray(y, dtype=float) - np.asarray(p, dtype=float))
    if not len(errors):
        return {"radiusSec": None, "nominalCoverage": .9, "n": 0, "status": "UNAVAILABLE"}
    # Split-conformal finite-sample order statistic; scenario correlation prevents IID coverage claims.
    rank = min(len(errors), int(np.ceil((len(errors)+1)*.9)))
    radius = float(np.sort(errors)[rank-1])
    return {"radiusSec": radius, "nominalCoverage": .9, "n": len(errors),
            "status": "SIMULATION_CALIBRATION_RESIDUAL_INTERVAL",
            "limitation": "Repeated snapshots are correlated; this is descriptive simulated-domain uncertainty, not guaranteed field coverage"}


def clustered_loss_difference(cluster_ids, differences, replicates=2000, seed=4016, confidence=.95):
    """Resample complete seed groups, retaining all families/trucks/cutoffs together."""
    values = np.asarray(differences, dtype=float)
    if len(values) != len(cluster_ids) or not len(values) or not np.isfinite(values).all():
        raise ValueError("Finite nonempty matched loss differences and cluster IDs are required")
    groups = sorted(set(cluster_ids))
    totals = np.asarray([values[np.asarray(cluster_ids) == group].sum() for group in groups])
    counts = np.asarray([sum(item == group for item in cluster_ids) for group in groups])
    result = {"mean": float(values.mean()), "cluster": "SEED_ACROSS_ALL_FAMILIES",
              "clusterCount": len(groups), "seedGroups": groups, "n": len(values),
              "replicates": replicates, "bootstrapSeed": seed, "confidenceLevel": confidence,
              "multiplicityCorrection": "NONE_DESCRIPTIVE_ONLY",
              "limitation": "Few independent seed clusters and correlated snapshots; descriptive simulation-domain uncertainty"}
    if len(groups) < 2:
        return {**result, "lower": None, "upper": None, "status": "UNAVAILABLE_SINGLE_CLUSTER"}
    draws = np.random.default_rng(seed).integers(0, len(groups), size=(replicates, len(groups)))
    samples = totals[draws].sum(axis=1) / counts[draws].sum(axis=1)
    tail = (1-confidence)/2
    return {**result, "lower": float(np.quantile(samples, tail)),
            "upper": float(np.quantile(samples, 1-tail)), "status": "PAIRED_SEED_CLUSTER_BOOTSTRAP"}
