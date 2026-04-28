"""Integration tests for the Flask app.

Uses a small in-memory MareeEnsemble fitted on the synthetic tiny_combined
fixture so tests run in seconds without depending on the production model
artifact on disk.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import joblib
import pandas as pd
import pytest

from src import config
from src.app.server import create_app
from src.models.baselines import make_logistic_regression
from src.models.ensemble import MareeConfig, MareeEnsemble
from src.preprocessing import build_preprocessor


@pytest.fixture()
def fitted_app(tmp_path: Path, tiny_combined: pd.DataFrame):
    """A Flask app loaded with a fast LR-based M.A.R.E.E. trained on the fixture."""
    cfg = MareeConfig(n_windows=3, base_factory=make_logistic_regression)
    ensemble = MareeEnsemble(ensemble_config=cfg)
    ensemble.fit_from_dataframe(tiny_combined, preprocessor_factory=build_preprocessor)

    model_path = tmp_path / "maree.joblib"
    joblib.dump(ensemble, model_path)

    demo_path = tmp_path / "demo.json"
    # Pick three rows from the fixture as demo samples
    demo_rows = []
    for i, (_, row) in enumerate(tiny_combined.head(3).iterrows()):
        rec = {"demo_id": f"sample_{i+1}",
               "true_label": int(row[config.LABEL_COL]),
               "true_label_name": "malware" if row[config.LABEL_COL] == 1 else "goodware"}
        for col in (*config.RAW_NUMERIC_FEATURES, *config.STRING_FEATURE_SOURCES):
            value = row[col]
            if hasattr(value, "item"):
                value = value.item()
            rec[col] = value
        demo_rows.append(rec)
    demo_path.write_text(json.dumps(demo_rows, default=str))

    app = create_app(model_path=model_path, demo_path=demo_path)
    app.config["TESTING"] = True
    return app


@pytest.fixture()
def client(fitted_app):
    return fitted_app.test_client()


@pytest.fixture()
def app_no_model(tmp_path: Path):
    """An app where the model file does NOT exist — exercises 503 paths."""
    app = create_app(
        model_path=tmp_path / "missing.joblib",
        demo_path=tmp_path / "missing-demo.json",
    )
    app.config["TESTING"] = True
    return app


class TestHealth:
    def test_health_returns_200_when_model_loaded(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "ok"
        assert body["model_loaded"] is True
        assert body["drift"]["available"] is True

    def test_health_when_model_missing(self, app_no_model):
        client = app_no_model.test_client()
        resp = client.get("/health")
        assert resp.status_code == 200  # /health still returns 200
        body = resp.get_json()
        assert body["model_loaded"] is False
        assert body["drift"]["available"] is False


class TestIndexAndDemo:
    def test_index_renders(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"M.A.R.E.E." in resp.data

    def test_demo_picker_renders_samples(self, client):
        resp = client.get("/demo")
        assert resp.status_code == 200
        assert b"sample_1" in resp.data


class TestPredict:
    def test_predict_demo_sample_renders_verdict(self, client):
        resp = client.post("/predict", data={"demo_id": "sample_1"})
        assert resp.status_code == 200
        assert b"verdict-pill" in resp.data

    def test_predict_unknown_demo_id_redirects(self, client):
        resp = client.post("/predict", data={"demo_id": "does-not-exist"})
        assert resp.status_code in (302, 303)

    def test_predict_with_no_model_returns_503(self, app_no_model):
        client = app_no_model.test_client()
        resp = client.post("/predict", data={"demo_id": "x"})
        assert resp.status_code == 503


class TestUpload:
    def test_upload_empty_form_redirects(self, client):
        resp = client.post("/upload", data={})
        assert resp.status_code in (302, 303)

    def test_upload_csv_returns_results(self, client, tiny_combined: pd.DataFrame):
        # Build a small CSV in memory from the fixture
        csv_buf = io.StringIO()
        tiny_combined.head(8).to_csv(csv_buf, index=False)
        csv_bytes = csv_buf.getvalue().encode()
        resp = client.post(
            "/upload",
            data={"file": (io.BytesIO(csv_bytes), "demo.csv")},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200
        assert b"Verdict breakdown" in resp.data
        # tiny_combined has Label column → metrics should appear
        assert b"AUC" in resp.data


class TestApiPredict:
    def test_api_predict_returns_json_verdict(self, client, tiny_combined: pd.DataFrame):
        sample = tiny_combined.iloc[0].to_dict()
        # Drop label / sample_date — the API is for new files
        sample.pop(config.LABEL_COL, None)
        sample.pop(config.SAMPLE_DATE_COL, None)
        resp = client.post("/api/predict", json=sample)
        assert resp.status_code == 200
        body = resp.get_json()
        assert "verdict" in body
        assert "probability" in body
        assert "triage" in body
        assert body["triage"]["backend"] == "template"

    def test_api_predict_rejects_non_json(self, client):
        resp = client.post("/api/predict", data="not json")
        assert resp.status_code == 400

    def test_api_predict_returns_503_without_model(self, app_no_model):
        client = app_no_model.test_client()
        resp = client.post("/api/predict", json={"BaseOfCode": 0})
        assert resp.status_code == 503
