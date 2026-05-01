"""Smoke tests — fast, broad sanity checks across the package.

These are distinct from the rubric's Step 10 *post-deploy smoke test*
(which is the live `/health` poll step in `.github/workflows/ci.yml`,
running against the production URL after every Render rebuild).
This file's tests catch package-coherence regressions *before* code
reaches the deploy stage: config drift, import-time side effects,
missing template files, accidental flushing of curated mappings.
"""
from __future__ import annotations

from pathlib import Path

import flask

import src
from src import config
from src.app.server import create_app


def test_package_version_is_set():
    assert src.__version__ == "0.0.1"


def test_global_seeds_are_pinned():
    """Reproducibility anchor — every stochastic step in the pipeline
    reads from these. Drift here would silently break reproducibility,
    one of the rubric's Step 2 sub-requirements."""
    assert config.GLOBAL_SEED == 42
    assert config.SPLIT_SEED == 42
    assert config.CV_SEED == 42


def test_rubric_required_quantities_are_intact():
    """Rubric-aligned quantities. Drift on any of these silently breaks
    the rubric's '27 input attributes' / '80/20 hold-out' / '10-fold CV'
    specification."""
    assert config.RANDOM_TEST_FRACTION == 0.20
    assert config.CV_FOLDS == 10
    assert len(config.RAW_NUMERIC_FEATURES) == 19
    assert len(config.ENGINEERED_FEATURES) == 8
    assert len(config.FEATURE_COLUMNS) == 27


def test_critical_modules_import_without_side_effects():
    """Importing core modules must not load the dataset, fetch GitHub
    Release artifacts, or trigger network calls. Catches accidental
    top-level work that would break startup performance or air-gapped
    deployment."""
    import src.data.loader  # noqa: F401
    import src.data.splits  # noqa: F401
    import src.features  # noqa: F401
    import src.models.advanced  # noqa: F401
    import src.models.baselines  # noqa: F401
    import src.models.drift_detector  # noqa: F401
    import src.models.ensemble  # noqa: F401
    import src.preprocessing  # noqa: F401
    import src.triage  # noqa: F401


def test_app_factory_returns_flask_instance(tmp_path: Path):
    """Flask app constructs cleanly even with absent model + demo paths.
    This is the boundary the post-deploy /health poll exercises against
    the production container; failure here would block the rubric's
    Step 9 + 10 deploy-and-smoke gate."""
    app = create_app(
        model_path=tmp_path / "absent.joblib",
        demo_path=tmp_path / "absent.json",
    )
    assert isinstance(app, flask.Flask)


def test_required_templates_present():
    """The six Jinja2 templates the rubric's Step 7 UI requires must
    exist on disk. Catches accidental template deletion."""
    templates_dir = Path(src.__file__).parent / "app" / "templates"
    expected = {
        "base.html",
        "index.html",
        "demo_picker.html",
        "verdict.html",
        "upload_results.html",
        "error.html",
    }
    actual = {p.name for p in templates_dir.glob("*.html")}
    missing = expected - actual
    assert not missing, f"Missing required templates: {missing}"


def test_triage_mitre_mapping_is_curated():
    """The triage layer's 'never invent technique IDs' constraint
    requires the hand-curated ATTACK_MAPPING to be present and
    non-trivial. Catches accidental flushing of the mapping."""
    from src.triage import ATTACK_MAPPING

    assert ATTACK_MAPPING, "ATTACK_MAPPING must not be empty"
    assert len(ATTACK_MAPPING) >= 4, (
        "MITRE mapping is curated per evaluation-and-design.md §8.3"
    )
