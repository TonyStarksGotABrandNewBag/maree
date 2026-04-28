"""Drift signals consumed by the M.A.R.E.E. ensemble.

Three signals, each a [0, 1] score where higher = more drift:

  1. per_model_accuracy_decay
     For each window-trained classifier, compare its accuracy on a held-out
     within-window validation tail vs. its accuracy on the most recent
     observed batch. A model whose recent accuracy is materially below its
     in-window accuracy is "drifting" — this signal weights it down.

  2. ensemble_disagreement
     Variance (or standard deviation) of per-model predicted probabilities
     for a given input. High disagreement = the council is divided = the
     prediction is uncertain.

  3. distribution_shift
     A coarse Population Stability Index (PSI) between the training
     distribution of a feature column and the current observed batch. We
     compute PSI for each numeric feature, average across features. PSI is
     a standard credit-risk drift metric; it's coarser than MMD but cheaper
     and interpretable to non-ML readers.

These signals feed into:
  - per-model vote weights (drift_detector.compute_weights)
  - the ensemble's abstention decision (ensemble.predict_with_uncertainty)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# ---------------------------------------------------------------------------
# 1. Per-model recent accuracy decay
# ---------------------------------------------------------------------------

def per_model_accuracy_decay(
    in_window_accuracies: np.ndarray,
    recent_accuracies: np.ndarray,
) -> np.ndarray:
    """Score each model by how much its accuracy has decayed since training.

    Args:
        in_window_accuracies: shape (K,). Accuracy each model achieved on
            its own held-out validation tail (its "training-era" baseline).
        recent_accuracies: shape (K,). Accuracy each model achieves on the
            most recent observed batch (the "deployment-era" measurement).

    Returns:
        shape (K,) of decay scores in [0, 1]. Higher = bigger decay.
        decay = max(0, in_window_acc - recent_acc) / in_window_acc
    """
    in_window = np.asarray(in_window_accuracies, dtype=np.float64)
    recent = np.asarray(recent_accuracies, dtype=np.float64)
    if in_window.shape != recent.shape:
        raise ValueError(f"shape mismatch: {in_window.shape} vs {recent.shape}")

    # Avoid division by zero — a model that scored 0 in-window has no
    # baseline to decay from; treat its decay as zero.
    safe = np.where(in_window > 1e-9, in_window, 1.0)
    raw = np.maximum(0.0, in_window - recent) / safe
    return np.clip(raw, 0.0, 1.0)


# ---------------------------------------------------------------------------
# 2. Ensemble disagreement
# ---------------------------------------------------------------------------

def ensemble_disagreement(per_model_proba: np.ndarray) -> np.ndarray:
    """Per-sample variance across the K models' positive-class probabilities.

    Args:
        per_model_proba: shape (K, N). Each row is one model's probability
            of the positive class for each of N samples.

    Returns:
        shape (N,) — std of per-model probabilities for each sample.
        Range: [0, 0.5]; we rescale to [0, 1] by multiplying by 2 so that
        downstream thresholds operate on a familiar 0..1 scale.
    """
    proba = np.asarray(per_model_proba, dtype=np.float64)
    if proba.ndim != 2:
        raise ValueError(f"expected 2D (K, N), got shape {proba.shape}")
    std = proba.std(axis=0, ddof=0)
    return np.clip(2.0 * std, 0.0, 1.0)


# ---------------------------------------------------------------------------
# 3. Population Stability Index (PSI)
# ---------------------------------------------------------------------------

def population_stability_index(
    train_values: np.ndarray,
    deploy_values: np.ndarray,
    n_buckets: int = 10,
) -> float:
    """PSI between train and deploy distributions for a single feature.

    PSI < 0.1   : no significant shift
    PSI 0.1-0.25: moderate shift, monitor
    PSI > 0.25  : large shift, retrain (industry rule of thumb).

    Returns the raw PSI (unbounded above), so callers can combine multiple
    feature PSIs by averaging or max-pooling.
    """
    train = np.asarray(train_values, dtype=np.float64)
    deploy = np.asarray(deploy_values, dtype=np.float64)
    train = train[np.isfinite(train)]
    deploy = deploy[np.isfinite(deploy)]
    if len(train) == 0 or len(deploy) == 0:
        return 0.0

    # Quantile-based buckets defined on the training distribution
    quantiles = np.linspace(0, 1, n_buckets + 1)
    edges = np.unique(np.quantile(train, quantiles))
    if len(edges) < 2:  # constant column — no PSI possible
        return 0.0

    train_counts, _ = np.histogram(train, bins=edges)
    deploy_counts, _ = np.histogram(deploy, bins=edges)

    # Smoothing to avoid log(0)
    eps = 1e-6
    train_pct = train_counts / max(train_counts.sum(), 1) + eps
    deploy_pct = deploy_counts / max(deploy_counts.sum(), 1) + eps
    return float(np.sum((deploy_pct - train_pct) * np.log(deploy_pct / train_pct)))


def average_psi(
    train_X: np.ndarray,
    deploy_X: np.ndarray,
    n_buckets: int = 10,
) -> float:
    """Average PSI across all numeric feature columns.

    Args:
        train_X: shape (N_train, F). Training features.
        deploy_X: shape (N_deploy, F). Currently observed features.

    Returns:
        Mean PSI across columns. A scalar drift score for the whole input.
    """
    train_X = np.asarray(train_X, dtype=np.float64)
    deploy_X = np.asarray(deploy_X, dtype=np.float64)
    if train_X.shape[1] != deploy_X.shape[1]:
        raise ValueError(
            f"feature-dim mismatch: train={train_X.shape[1]} deploy={deploy_X.shape[1]}"
        )
    if len(train_X) == 0 or len(deploy_X) == 0:
        return 0.0
    psis = [
        population_stability_index(train_X[:, j], deploy_X[:, j], n_buckets)
        for j in range(train_X.shape[1])
    ]
    return float(np.mean(psis))


# ---------------------------------------------------------------------------
# Combined per-model weight
# ---------------------------------------------------------------------------

@dataclass
class WeightingConfig:
    """Knobs for the per-model vote weighting in M.A.R.E.E.

    - recency_alpha controls how strongly newer models are favored.
    - decay_penalty controls how strongly we down-weight models showing
      accuracy decay since training.
    """
    recency_alpha: float = 1.0     # newest model gets weight ~e^0=1; oldest gets e^(-recency_alpha)
    decay_penalty: float = 2.0     # multiplier on the decay score


def compute_weights(
    in_window_accuracies: np.ndarray,
    recent_accuracies: np.ndarray | None = None,
    config: WeightingConfig | None = None,
) -> np.ndarray:
    """Compute normalized per-model vote weights.

    Args:
        in_window_accuracies: shape (K,). One per ensemble member, ordered
            oldest-to-newest. The newest model is index K-1.
        recent_accuracies: optional shape (K,). If None, decay penalty is
            zero (treat all models as fresh). Useful before any drift signal
            has been observed.
        config: weighting hyperparameters.

    Returns:
        shape (K,) of weights summing to 1.
    """
    config = config or WeightingConfig()
    K = len(in_window_accuracies)

    # Recency: newest member gets exp(0), oldest gets exp(-recency_alpha)
    positions = np.arange(K, dtype=np.float64)
    recency = np.exp(-config.recency_alpha * (K - 1 - positions) / max(K - 1, 1))

    # Quality: in-window accuracy itself
    quality = np.asarray(in_window_accuracies, dtype=np.float64)

    # Decay penalty (reduces weight for models showing recent decay)
    if recent_accuracies is None:
        penalty = np.ones(K)
    else:
        decay = per_model_accuracy_decay(in_window_accuracies, recent_accuracies)
        penalty = np.exp(-config.decay_penalty * decay)

    raw = recency * quality * penalty
    if raw.sum() <= 0:  # degenerate case — fall back to uniform
        return np.ones(K) / K
    return raw / raw.sum()
