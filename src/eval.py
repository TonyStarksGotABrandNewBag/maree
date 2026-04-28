"""Renders the headline table from src/train.py results.

Usage:
    .venv/bin/python -m src.eval

Reads results/phase_d_results.json (produced by src.train.run_full_evaluation())
and prints the headline finding: per-model AUC and Accuracy under random vs.
temporal protocols, with mean ± std across CV folds and the hold-out test
result on a single row.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src import config

RESULTS_DIR = config.PROJECT_ROOT / "results"


def load_results(path: Path | None = None) -> dict:
    """Load results either from the monolithic JSON (legacy) or assemble
    from per-(model, protocol, stage) part files written by src.run_one.

    The per-part assembly is preferred because it survives crashes in
    individual model runs.
    """
    if path is not None and path.is_file():
        return json.loads(path.read_text())

    parts_dir = RESULTS_DIR / "parts"
    if parts_dir.is_dir() and any(parts_dir.glob("*.json")):
        return assemble_from_parts(parts_dir)

    legacy = RESULTS_DIR / "phase_d_results.json"
    if legacy.is_file():
        return json.loads(legacy.read_text())

    raise FileNotFoundError(
        f"No results found. Run `./scripts/run_phase_d.sh` first."
    )


def assemble_from_parts(parts_dir: Path) -> dict:
    """Combine per-(model, protocol, stage) JSON files into the dict shape
    that headline_table() and render_report() expect."""
    out = {"cv_random": [], "cv_temporal": [], "holdout_random": [], "holdout_temporal": []}
    for part_file in sorted(parts_dir.glob("*.json")):
        records = json.loads(part_file.read_text())
        # Filename pattern: {stage}_{protocol}_{model}.json
        name = part_file.stem
        if name.startswith("cv_random_"):
            out["cv_random"].extend(records)
        elif name.startswith("cv_temporal_"):
            out["cv_temporal"].extend(records)
        elif name.startswith("holdout_random_"):
            out["holdout_random"].extend(records)
        elif name.startswith("holdout_temporal_"):
            out["holdout_temporal"].extend(records)
    return out


def cv_summary(cv_records: list[dict]) -> pd.DataFrame:
    """mean ± std AUC and accuracy per (model, protocol)."""
    df = pd.DataFrame(cv_records)
    grouped = df.groupby(["model_name", "protocol"]).agg(
        auc_mean=("auc", "mean"),
        auc_std=("auc", "std"),
        acc_mean=("accuracy", "mean"),
        acc_std=("accuracy", "std"),
        fit_seconds_mean=("fit_seconds", "mean"),
    )
    return grouped.round(4)


def holdout_summary(records: list[dict]) -> pd.DataFrame:
    """One row per (model, protocol) for the hold-out test eval."""
    df = pd.DataFrame(records)
    return df.set_index(["model_name", "protocol"])[
        ["auc", "accuracy", "n_train", "n_test", "fit_seconds"]
    ].round(4)


def headline_table(results: dict) -> pd.DataFrame:
    """The single table that goes into evaluation-and-design.md.

    Columns: model_name, random_cv_auc, temporal_cv_auc, drift_gap,
             random_holdout_auc, temporal_holdout_auc.
    """
    cv_df = pd.DataFrame(results["cv_random"] + results["cv_temporal"])
    cv_summary_df = cv_df.groupby(["model_name", "protocol"]).agg(
        cv_auc_mean=("auc", "mean"),
        cv_auc_std=("auc", "std"),
    ).reset_index()
    cv_pivot = cv_summary_df.pivot(index="model_name", columns="protocol", values="cv_auc_mean")
    cv_std_pivot = cv_summary_df.pivot(index="model_name", columns="protocol", values="cv_auc_std")

    ho_df = pd.DataFrame(results["holdout_random"] + results["holdout_temporal"])
    ho_auc = ho_df.pivot(index="model_name", columns="protocol", values="auc")
    ho_acc = ho_df.pivot(index="model_name", columns="protocol", values="accuracy")

    out = pd.DataFrame(index=cv_pivot.index)
    out["random_cv_auc"] = cv_pivot["random"].round(4)
    out["random_cv_std"] = cv_std_pivot["random"].round(4)
    out["temporal_cv_auc"] = cv_pivot["temporal"].round(4)
    out["temporal_cv_std"] = cv_std_pivot["temporal"].round(4)
    out["drift_gap_cv_auc"] = (cv_pivot["random"] - cv_pivot["temporal"]).round(4)
    out["random_holdout_auc"] = ho_auc["random"].round(4)
    out["temporal_holdout_auc"] = ho_auc["temporal"].round(4)
    out["drift_gap_holdout_auc"] = (ho_auc["random"] - ho_auc["temporal"]).round(4)
    out["random_holdout_acc"] = ho_acc["random"].round(4)
    out["temporal_holdout_acc"] = ho_acc["temporal"].round(4)
    out["drift_gap_holdout_acc"] = (ho_acc["random"] - ho_acc["temporal"]).round(4)

    # Order rows: baselines first, then advanced
    desired_order = [
        "logistic_regression", "decision_tree", "random_forest", "torch_mlp",
        "xgboost", "lightgbm", "catboost",
    ]
    out = out.reindex([m for m in desired_order if m in out.index])
    return out


def render_report(results: dict) -> str:
    """Markdown report for evaluation-and-design.md §4."""
    headline = headline_table(results)
    cv_summary_df = pd.concat([
        pd.DataFrame(results["cv_random"]),
        pd.DataFrame(results["cv_temporal"]),
    ])
    cv_per_protocol = cv_summary(cv_summary_df.to_dict(orient="records"))

    md_lines = []
    md_lines.append("### Headline finding — random vs temporal hold-out, all 7 models\n")
    md_lines.append("AUC degrades modestly under temporal evaluation; accuracy at the 0.5 threshold collapses. The asymmetry is the calibration-vs-ranking distinction (Pendlebury et al., 2019): models still rank samples correctly, but the decision threshold no longer separates classes after distribution shift.\n")
    md_lines.append("| Model | Random hold-out AUC | Temporal hold-out AUC | Δ AUC | Random hold-out ACC | Temporal hold-out ACC | Δ ACC |")
    md_lines.append("|---|---|---|---|---|---|---|")
    for name, row in headline.iterrows():
        md_lines.append(
            f"| {name} | "
            f"{row['random_holdout_auc']:.4f} | "
            f"{row['temporal_holdout_auc']:.4f} | "
            f"−{row['drift_gap_holdout_auc']:.4f} | "
            f"{row['random_holdout_acc']:.4f} | "
            f"{row['temporal_holdout_acc']:.4f} | "
            f"−{row['drift_gap_holdout_acc']:.4f} |"
        )

    md_lines.append("\n### Cross-validation AUC under both protocols\n")
    md_lines.append("CV is computed within the *training portion* of each split, so both protocols see internally i.i.d. data here — the temporal-vs-random asymmetry only appears when testing on post-cutoff data the model has never seen (the hold-out table above).\n")
    md_lines.append("| Model | Random CV AUC | Temporal CV AUC |")
    md_lines.append("|---|---|---|")
    for name, row in headline.iterrows():
        md_lines.append(
            f"| {name} | "
            f"{row['random_cv_auc']:.4f} ± {row['random_cv_std']:.4f} | "
            f"{row['temporal_cv_auc']:.4f} ± {row['temporal_cv_std']:.4f} |"
        )

    md_lines.append("\n### Full CV statistics (mean ± std across 10 folds)\n")
    md_lines.append("| Model | Protocol | AUC | Accuracy | Mean fit (s) |")
    md_lines.append("|---|---|---|---|---|")
    for (model, protocol), row in cv_per_protocol.iterrows():
        md_lines.append(
            f"| {model} | {protocol} | "
            f"{row['auc_mean']:.4f} ± {row['auc_std']:.4f} | "
            f"{row['acc_mean']:.4f} ± {row['acc_std']:.4f} | "
            f"{row['fit_seconds_mean']:.1f} |"
        )

    return "\n".join(md_lines)


def main() -> int:
    results = load_results()
    print(headline_table(results).to_string())
    print()
    print(render_report(results))
    out = RESULTS_DIR / "phase_d_report.md"
    out.write_text(render_report(results))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
