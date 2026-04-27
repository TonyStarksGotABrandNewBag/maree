"""Phase B EDA — Brazilian Malware Dataset (Ceschin et al., 2018).

Produces:
  1. Schema inventory: malware vs goodware columns, dtypes, overlap, gaps
  2. Sample counts per day, per month, per year
  3. Class balance over time (the drift-narrative setup)
  4. Empty-day count and pattern
  5. Notes on label construction (the dataset stores label by *file location*,
     not as an explicit column)

Outputs:
  - notebooks/eda_outputs/per_day_counts.csv
  - notebooks/eda_outputs/per_month_counts.csv
  - notebooks/eda_outputs/schema_inventory.txt
  - notebooks/eda_outputs/class_balance_over_time.png
  - notebooks/eda_outputs/sample_counts_over_time.png

Run: .venv/bin/python notebooks/02_eda.py
"""

from __future__ import annotations

from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")  # headless
import matplotlib.pyplot as plt
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data" / "brazilian-malware-dataset" / "goodware-malware"
MALWARE_DIR = DATA_ROOT / "malware-by-day"
GOODWARE_CSV = DATA_ROOT / "goodware.csv"
OUT_DIR = PROJECT_ROOT / "notebooks" / "eda_outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def schema_inventory() -> tuple[set[str], set[str]]:
    """Inventory malware-day vs goodware columns, surface overlap and gaps."""
    # Find first non-empty malware-day file for schema
    sample_path = None
    for p in sorted(MALWARE_DIR.glob("*.csv")):
        if p.stat().st_size > 0:
            sample_path = p
            break
    if sample_path is None:
        sys.exit(f"No non-empty malware CSVs found in {MALWARE_DIR}")

    mw = pd.read_csv(sample_path, nrows=10)
    gw = pd.read_csv(GOODWARE_CSV, nrows=10)
    mw_cols, gw_cols = set(mw.columns), set(gw.columns)

    only_mw = mw_cols - gw_cols
    only_gw = gw_cols - mw_cols
    shared = mw_cols & gw_cols

    out = OUT_DIR / "schema_inventory.txt"
    with out.open("w") as f:
        f.write("=== Schema inventory: Brazilian Malware Dataset ===\n\n")
        f.write(f"Sample malware file: {sample_path.name} ({len(mw.columns)} columns)\n")
        f.write(f"Goodware file: goodware.csv ({len(gw.columns)} columns)\n\n")
        f.write(f"Shared columns ({len(shared)}):\n")
        for c in sorted(shared):
            f.write(f"  - {c} ({mw[c].dtype})\n")
        f.write(f"\nMalware-only columns ({len(only_mw)}):\n")
        for c in sorted(only_mw):
            f.write(f"  - {c} ({mw[c].dtype})\n")
        f.write(f"\nGoodware-only columns ({len(only_gw)}):\n")
        for c in sorted(only_gw):
            f.write(f"  - {c} ({gw[c].dtype})\n")
        f.write("\n=== Notes ===\n")
        f.write(
            "- The dataset has NO 'Label' column. Class is encoded by file location:\n"
            "  malware samples live in malware-by-day/YYYY-MM-DD.csv,\n"
            "  goodware samples live in goodware.csv.\n"
        )
        f.write(
            "- The Quantic PDF specifies 27 input attributes + a 'Label' column.\n"
            "  The Brazilian dataset has more raw columns. We will select the\n"
            "  numeric subset, drop hash/identifier columns (MD5, SHA1, Name),\n"
            "  optionally feature-engineer from string columns (ImportedDlls\n"
            "  cardinality, etc.), and construct the Label column from file source.\n"
        )
    print(f"Wrote {out}")
    return mw_cols, gw_cols


def per_day_counts() -> pd.DataFrame:
    """Count malware samples per day across all 2,797 daily files."""
    rows = []
    files = sorted(MALWARE_DIR.glob("*.csv"))
    for p in files:
        date = pd.to_datetime(p.stem, errors="coerce")
        if pd.isna(date):
            continue
        size_bytes = p.stat().st_size
        if size_bytes == 0:
            n = 0
        else:
            # Cheap line count — header + rows. Latin-1 to tolerate the
            # non-UTF-8 bytes (filenames carry Portuguese characters).
            with p.open(encoding="latin-1") as f:
                n = sum(1 for _ in f) - 1
        rows.append({"date": date, "n_malware": max(n, 0)})
    df = pd.DataFrame(rows)
    out = OUT_DIR / "per_day_counts.csv"
    df.to_csv(out, index=False)
    print(f"Wrote {out}: {len(df):,} day-rows, {df['n_malware'].sum():,} total malware samples")
    return df


def per_month_aggregations(daily: pd.DataFrame) -> pd.DataFrame:
    """Roll daily malware counts into monthly bins for trend visualization."""
    monthly = (
        daily.assign(month=lambda d: d["date"].dt.to_period("M"))
        .groupby("month")["n_malware"]
        .agg(["sum", "mean", "max", "count"])
        .rename(columns={"sum": "malware_total", "mean": "malware_per_day_mean",
                         "max": "malware_per_day_max", "count": "n_days"})
    )
    out = OUT_DIR / "per_month_counts.csv"
    monthly.to_csv(out)
    print(f"Wrote {out}: {len(monthly)} months covered")
    return monthly


def goodware_summary() -> int:
    """How big is the goodware corpus, and what's its temporal range?"""
    n_rows = sum(1 for _ in GOODWARE_CSV.open(encoding="latin-1")) - 1
    print(f"Goodware: {n_rows:,} total samples")
    # Goodware has FormatedTimeDateStamp — PE-embedded, forgeable, but the only
    # temporal signal we have for goodware. Surface its range.
    tds = pd.read_csv(GOODWARE_CSV, usecols=["FormatedTimeDateStamp"])
    tds["FormatedTimeDateStamp"] = pd.to_datetime(
        tds["FormatedTimeDateStamp"], errors="coerce"
    )
    valid = tds.dropna()
    print(
        f"Goodware FormatedTimeDateStamp range "
        f"({len(valid):,}/{len(tds):,} valid): "
        f"{valid['FormatedTimeDateStamp'].min()} → "
        f"{valid['FormatedTimeDateStamp'].max()}"
    )
    return n_rows


def plot_sample_counts(daily: pd.DataFrame, monthly: pd.DataFrame) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(14, 8))

    # Daily counts
    axes[0].plot(daily["date"], daily["n_malware"], linewidth=0.5, color="#c0392b")
    axes[0].set_title("Malware samples per day (Brazilian Malware Dataset)")
    axes[0].set_ylabel("Samples / day")
    axes[0].grid(True, alpha=0.3)

    # Monthly aggregation
    monthly_dates = pd.PeriodIndex(monthly.index).to_timestamp()
    axes[1].bar(monthly_dates, monthly["malware_total"], width=20, color="#2c3e50")
    axes[1].set_title("Malware samples per month")
    axes[1].set_ylabel("Samples / month")
    axes[1].set_xlabel("Date")
    axes[1].grid(True, alpha=0.3, axis="y")

    plt.tight_layout()
    out = OUT_DIR / "sample_counts_over_time.png"
    plt.savefig(out, dpi=120, bbox_inches="tight")
    plt.close()
    print(f"Wrote {out}")


def empty_day_pattern(daily: pd.DataFrame) -> None:
    """Many days have zero malware. Surface the pattern."""
    n_total = len(daily)
    n_empty = int((daily["n_malware"] == 0).sum())
    print(
        f"\nEmpty-day pattern: {n_empty:,} of {n_total:,} days "
        f"({100 * n_empty / n_total:.1f}%) have zero malware samples"
    )
    by_year = (
        daily.assign(year=lambda d: d["date"].dt.year)
        .assign(is_empty=lambda d: d["n_malware"] == 0)
        .groupby("year")
        .agg(n_days=("date", "count"), n_empty=("is_empty", "sum"),
             total_malware=("n_malware", "sum"))
    )
    by_year["pct_empty"] = (100 * by_year["n_empty"] / by_year["n_days"]).round(1)
    print("\nPer-year breakdown:")
    print(by_year.to_string())


def main() -> int:
    if not MALWARE_DIR.is_dir():
        sys.exit(f"Dataset not found at {DATA_ROOT}. Run scripts/download_data.py first.")

    print("=== Phase B EDA: Brazilian Malware Dataset ===\n")
    schema_inventory()
    print()
    daily = per_day_counts()
    monthly = per_month_aggregations(daily)
    print()
    goodware_summary()
    empty_day_pattern(daily)
    plot_sample_counts(daily, monthly)
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
