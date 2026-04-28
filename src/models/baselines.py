"""Baseline classifiers required by the Quantic rubric (Step 6).

  - Logistic Regression
  - Decision Tree
  - Random Forest
  - PyTorch MLP

All four follow a uniform sklearn-compatible interface: `.fit(X, y)`,
`.predict(X)`, `.predict_proba(X)`. The PyTorch MLP wraps a small feed-
forward network in this interface so the train / eval orchestrators can
treat it like any sklearn estimator.

Hyperparameters are kept conservative and explicit. The capstone is not
about hyperparameter Olympics; it is about honest evaluation under
temporal drift. Aggressive tuning happens in Phase E for the M.A.R.E.E.
ensemble itself.
"""

from __future__ import annotations

import numpy as np
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier

from src import config

# torch is imported lazily inside TorchMLPClassifier — see _MLPNet / fit /
# _resolve_device. Eagerly importing torch breaks any subprocess that also
# uses XGBoost / LightGBM / CatBoost (libomp conflict on macOS). The
# deferred import keeps non-MLP runs torch-free.


def make_logistic_regression() -> LogisticRegression:
    return LogisticRegression(
        max_iter=2000,
        solver="liblinear",  # robust for moderate-dimensional binary tasks
        random_state=config.GLOBAL_SEED,
    )


def make_decision_tree() -> DecisionTreeClassifier:
    return DecisionTreeClassifier(
        max_depth=12,
        min_samples_leaf=20,
        random_state=config.GLOBAL_SEED,
    )


def make_random_forest() -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=200,
        max_depth=20,
        min_samples_leaf=5,
        # Capped at 4 to avoid OpenMP collisions with XGBoost/LightGBM/CatBoost
        # when several heavy classifiers run sequentially in the same process.
        n_jobs=4,
        random_state=config.GLOBAL_SEED,
    )


# ---------------------------------------------------------------------------
# PyTorch MLP wrapped in the sklearn estimator interface
# ---------------------------------------------------------------------------

def _build_mlp_net(input_dim: int, hidden: tuple[int, ...], dropout: float):
    """Build the MLP. Imports torch lazily to avoid OpenMP conflicts."""
    import torch.nn as nn

    class _MLPNet(nn.Module):
        def __init__(self, input_dim_: int, hidden_: tuple[int, ...], dropout_: float):
            super().__init__()
            layers: list = []
            prev = input_dim_
            for h in hidden_:
                layers += [nn.Linear(prev, h), nn.ReLU(), nn.Dropout(dropout_)]
                prev = h
            layers.append(nn.Linear(prev, 1))  # binary logit
            self.net = nn.Sequential(*layers)

        def forward(self, x):
            return self.net(x).squeeze(-1)

    return _MLPNet(input_dim, hidden, dropout)


class TorchMLPClassifier(BaseEstimator, ClassifierMixin):
    """A small PyTorch MLP that quacks like an sklearn estimator.

    Conservative defaults that fit comfortably on CPU.
    """

    def __init__(
        self,
        hidden: tuple[int, ...] = (128, 64),
        dropout: float = 0.2,
        epochs: int = 30,
        batch_size: int = 256,
        lr: float = 1e-3,
        weight_decay: float = 1e-5,
        random_state: int = config.GLOBAL_SEED,
        device: str | None = None,
    ):
        self.hidden = hidden
        self.dropout = dropout
        self.epochs = epochs
        self.batch_size = batch_size
        self.lr = lr
        self.weight_decay = weight_decay
        self.random_state = random_state
        self.device = device

    # sklearn estimator boilerplate
    def get_params(self, deep: bool = True) -> dict:
        return {
            "hidden": self.hidden,
            "dropout": self.dropout,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "lr": self.lr,
            "weight_decay": self.weight_decay,
            "random_state": self.random_state,
            "device": self.device,
        }

    def _resolve_device(self):
        import torch

        if self.device is not None:
            return torch.device(self.device)
        if torch.cuda.is_available():
            return torch.device("cuda")
        # Note: skipping MPS even when available. On macOS, the MPS backend
        # has been observed to segfault when loaded after sklearn estimators
        # have already trained in the same process (libomp / Metal init race).
        # CPU is fast enough for our 27-feature, ~40k-row problem
        # (~5s per 30 epochs); reliability beats marginal speedup.
        return torch.device("cpu")

    def fit(self, X: np.ndarray, y: np.ndarray) -> TorchMLPClassifier:
        import torch
        import torch.nn as nn

        torch.manual_seed(self.random_state)
        np.random.seed(self.random_state)

        device = self._resolve_device()
        self._device_ = device
        self.classes_ = np.unique(y)
        if len(self.classes_) != 2:
            raise ValueError(
                f"TorchMLPClassifier supports binary classification only; "
                f"got {len(self.classes_)} classes."
            )

        X_t = torch.as_tensor(X, dtype=torch.float32, device=device)
        y_t = torch.as_tensor(y, dtype=torch.float32, device=device)

        self.net_ = _build_mlp_net(input_dim=X.shape[1], hidden=self.hidden, dropout=self.dropout).to(device)
        optim = torch.optim.Adam(self.net_.parameters(), lr=self.lr, weight_decay=self.weight_decay)
        # BCEWithLogitsLoss handles class imbalance via pos_weight
        pos_weight = torch.tensor(
            [(y_t == 0).sum().item() / max((y_t == 1).sum().item(), 1)],
            device=device,
        )
        loss_fn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

        n = X_t.shape[0]
        idx = torch.arange(n, device=device)
        for _ in range(self.epochs):
            perm = idx[torch.randperm(n, device=device)]
            for start in range(0, n, self.batch_size):
                batch_idx = perm[start:start + self.batch_size]
                logits = self.net_(X_t[batch_idx])
                loss = loss_fn(logits, y_t[batch_idx])
                optim.zero_grad()
                loss.backward()
                optim.step()
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        import torch

        if not hasattr(self, "net_"):
            raise RuntimeError("Call fit() before predict_proba().")
        device = self._device_
        self.net_.eval()
        with torch.no_grad():
            X_t = torch.as_tensor(X, dtype=torch.float32, device=device)
            probs = torch.sigmoid(self.net_(X_t)).cpu().numpy()
        return np.column_stack([1.0 - probs, probs])

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def make_torch_mlp() -> TorchMLPClassifier:
    return TorchMLPClassifier(
        hidden=(128, 64),
        dropout=0.2,
        epochs=30,
        batch_size=256,
        lr=1e-3,
        random_state=config.GLOBAL_SEED,
    )


# ---------------------------------------------------------------------------
# Convenience: build all four baselines as a name → factory mapping
# ---------------------------------------------------------------------------

BASELINE_FACTORIES = {
    "logistic_regression": make_logistic_regression,
    "decision_tree": make_decision_tree,
    "random_forest": make_random_forest,
    "torch_mlp": make_torch_mlp,
}
