"""M.A.R.E.E. Flask app — the user-visible artifact.

Endpoints:
  GET  /                  Landing page with two CTAs: try sample / upload file
  GET  /demo              Demo-sample picker (5 pre-loaded rows from the
                          temporal hold-out, exhibiting real drift)
  POST /predict           Single-sample prediction. Form fields are the 27
                          features; renders the verdict + LLM triage.
  POST /upload            CSV upload. Renders per-row verdicts + (if a Label
                          column is present) AUC / accuracy / confusion matrix.
  GET  /health            JSON health check for the CI/CD smoke test.
  GET  /api/predict       Programmatic JSON endpoint (used by the integration
                          test). Accepts a single sample as JSON body.

Model and demo samples are loaded at startup from `artifacts/`. The drift
status indicator at the top of every page reports the days-since-newest-
window-trained and per-window calibrated accuracies.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# Cap thread pools BEFORE importing native ML libs (same pattern as elsewhere)
os.environ.setdefault("OMP_NUM_THREADS", "4")
os.environ.setdefault("MKL_NUM_THREADS", "4")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "4")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import joblib
import numpy as np
import pandas as pd
from flask import Flask, jsonify, redirect, render_template, request, url_for
from sklearn.metrics import accuracy_score, confusion_matrix, roc_auc_score

from src import config
from src.features import engineer_string_features
from src.models.ensemble import (
    VERDICT_ALLOWED,
    VERDICT_BLOCKED_MALWARE,
    VERDICT_BLOCKED_UNCERTAIN,
    MareePrediction,
)
from src.triage import explain as triage_explain

ARTIFACTS_DIR = config.PROJECT_ROOT / "artifacts"
MODEL_PATH = ARTIFACTS_DIR / "maree_production.joblib"
DEMO_PATH = ARTIFACTS_DIR / "demo_samples.json"


def create_app(*, model_path: Path = MODEL_PATH, demo_path: Path = DEMO_PATH) -> Flask:
    """App factory. Tests can pass alternate paths."""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB upload cap

    # Load model + demo samples at startup. If the model file is missing,
    # the app still starts (so /health works for orchestration) but
    # prediction routes will return a structured error.
    if model_path.exists():
        app.config["MAREE_MODEL"] = joblib.load(model_path)
    else:
        app.config["MAREE_MODEL"] = None

    if demo_path.exists():
        app.config["DEMO_SAMPLES"] = json.loads(demo_path.read_text())
    else:
        app.config["DEMO_SAMPLES"] = []

    register_routes(app)
    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _drift_status(model) -> dict:
    """Drift indicator shown at the top of every page."""
    if model is None:
        return {"available": False}
    accuracies = list(model.in_window_accuracies_)
    return {
        "available": True,
        "n_active_windows": int(model.n_active_),
        "newest_window_accuracy": float(accuracies[-1]) if accuracies else 0.0,
        "oldest_window_accuracy": float(accuracies[0]) if accuracies else 0.0,
        "per_window_accuracies": [round(float(a), 3) for a in accuracies],
    }


def _row_from_form(form) -> dict:
    """Convert a form POST into a single-sample dict matching the schema."""
    row: dict = {}
    for col in config.RAW_NUMERIC_FEATURES:
        raw = form.get(col, "").strip()
        try:
            row[col] = float(raw) if raw else 0.0
        except ValueError:
            row[col] = 0.0
    for col in config.STRING_FEATURE_SOURCES:
        row[col] = form.get(col, "")
    return row


def _predict_one(model, sample: dict) -> MareePrediction:
    """Run M.A.R.E.E. on a single-sample dict."""
    df = pd.DataFrame([sample])
    df[config.LABEL_COL] = 0  # placeholder; unused by predict_*_from_dataframe
    verdicts = model.predict_with_uncertainty(df)
    return verdicts[0]


def _enriched_sample_for_triage(sample: dict) -> dict:
    """Engineer string features so the triage layer sees the same columns
    M.A.R.E.E. did. Returns a flat dict the triage explainer expects."""
    df = pd.DataFrame([sample])
    enriched = engineer_string_features(df).iloc[0].to_dict()
    return enriched


def _verdict_badge_class(verdict: str) -> str:
    """CSS class for the verdict pill."""
    if verdict == VERDICT_ALLOWED:
        return "verdict-allowed"
    if verdict == VERDICT_BLOCKED_MALWARE:
        return "verdict-malware"
    return "verdict-uncertain"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def register_routes(app: Flask) -> None:

    @app.route("/")
    def index():
        return render_template(
            "index.html",
            drift=_drift_status(app.config["MAREE_MODEL"]),
            demo_count=len(app.config["DEMO_SAMPLES"]),
        )

    @app.route("/demo")
    def demo_picker():
        return render_template(
            "demo_picker.html",
            drift=_drift_status(app.config["MAREE_MODEL"]),
            samples=app.config["DEMO_SAMPLES"],
        )

    @app.route("/predict", methods=["POST"])
    def predict():
        model = app.config["MAREE_MODEL"]
        if model is None:
            return render_template(
                "error.html",
                drift=_drift_status(None),
                message="Production model not loaded — run `python scripts/train_production_model.py` first.",
            ), 503

        # Two paths: form-fields submission or "use demo sample N"
        demo_id = request.form.get("demo_id", "").strip()
        if demo_id:
            sample = next(
                (s for s in app.config["DEMO_SAMPLES"] if s["demo_id"] == demo_id),
                None,
            )
            if sample is None:
                return redirect(url_for("demo_picker"))
            true_label = sample.get("true_label_name", "unknown")
        else:
            sample = _row_from_form(request.form)
            true_label = None

        prediction = _predict_one(model, sample)
        triage = triage_explain(prediction, _enriched_sample_for_triage(sample))

        return render_template(
            "verdict.html",
            drift=_drift_status(model),
            sample=sample,
            prediction=prediction,
            badge_class=_verdict_badge_class(prediction.verdict),
            triage=triage,
            true_label=true_label,
        )

    @app.route("/upload", methods=["POST"])
    def upload():
        model = app.config["MAREE_MODEL"]
        if model is None:
            return render_template(
                "error.html",
                drift=_drift_status(None),
                message="Production model not loaded — run `python scripts/train_production_model.py` first.",
            ), 503

        upload_file = request.files.get("file")
        if upload_file is None or upload_file.filename == "":
            return redirect(url_for("index"))

        try:
            df = pd.read_csv(upload_file, encoding="latin-1", low_memory=False)
        except Exception as exc:  # pragma: no cover  (rendered to user)
            return render_template(
                "error.html",
                drift=_drift_status(model),
                message=f"Could not parse uploaded CSV: {exc}",
            ), 400

        # Predict on the uploaded rows
        df_for_predict = df.copy()
        if config.LABEL_COL not in df_for_predict.columns:
            df_for_predict[config.LABEL_COL] = 0  # placeholder

        verdicts = model.predict_with_uncertainty(df_for_predict)
        proba = model.predict_proba_from_dataframe(df_for_predict)[:, 1]
        per_row = [
            {
                "row": i,
                "verdict": v.verdict,
                "probability": round(v.probability, 4),
                "confidence": round(v.confidence, 4),
                "badge": _verdict_badge_class(v.verdict),
            }
            for i, v in enumerate(verdicts)
        ]

        # If the upload contained Labels, compute evaluation metrics
        metrics = None
        if config.LABEL_COL in df.columns:
            y_true = df[config.LABEL_COL].astype(int).to_numpy()
            block_decision = np.array([int(v.is_malware_decision) for v in verdicts])
            cm = confusion_matrix(y_true, block_decision, labels=[0, 1])
            metrics = {
                "auc": round(float(roc_auc_score(y_true, proba)), 4),
                "accuracy_block": round(float(accuracy_score(y_true, block_decision)), 4),
                "confusion": cm.tolist(),
                "n": int(len(y_true)),
            }

        return render_template(
            "upload_results.html",
            drift=_drift_status(model),
            n_total=len(df),
            verdict_counts={
                "allowed": sum(v.verdict == VERDICT_ALLOWED for v in verdicts),
                "blocked_malware": sum(v.verdict == VERDICT_BLOCKED_MALWARE for v in verdicts),
                "blocked_uncertain": sum(v.verdict == VERDICT_BLOCKED_UNCERTAIN for v in verdicts),
            },
            per_row=per_row[:200],  # cap rendered rows for very large uploads
            n_rendered=min(200, len(per_row)),
            metrics=metrics,
        )

    @app.route("/api/predict", methods=["POST"])
    def api_predict():
        """Programmatic JSON endpoint. Accepts a single sample as JSON.

        Missing numeric features are backfilled with 0.0 (treated as
        "unobserved"); missing string features are backfilled with "".
        Same lenient policy as the HTML form route, so an integration test
        can submit a partial sample.
        """
        model = app.config["MAREE_MODEL"]
        if model is None:
            return jsonify({"error": "model_not_loaded"}), 503
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify({"error": "expected_json_object"}), 400

        # Backfill any missing required columns with neutral values.
        sample: dict = {}
        for col in config.RAW_NUMERIC_FEATURES:
            v = body.get(col, 0.0)
            try:
                sample[col] = float(v)
            except (TypeError, ValueError):
                sample[col] = 0.0
        for col in config.STRING_FEATURE_SOURCES:
            sample[col] = body.get(col, "") or ""

        try:
            prediction = _predict_one(model, sample)
            triage = triage_explain(prediction, _enriched_sample_for_triage(sample))
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
        return jsonify({
            "verdict": prediction.verdict,
            "probability": prediction.probability,
            "confidence": prediction.confidence,
            "is_malware_decision": prediction.is_malware_decision,
            "triage": {
                "summary": triage.summary,
                "why": triage.why,
                "attack_techniques": triage.attack_techniques,
                "recommended_actions": triage.recommended_actions,
                "backend": triage.backend,
            },
        })

    @app.route("/health")
    def health():
        """CI/CD smoke test endpoint. Returns model + drift status."""
        model = app.config["MAREE_MODEL"]
        return jsonify({
            "status": "ok",
            "model_loaded": model is not None,
            "drift": _drift_status(model),
            "demo_samples": len(app.config["DEMO_SAMPLES"]),
        })


# Module-level app for `flask --app src.app.server run` and gunicorn.
app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
