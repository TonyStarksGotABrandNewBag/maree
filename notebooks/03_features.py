"""Phase B EDA — Feature inventory, missingness, and distributions.

Loads a stratified time sample (one month per year of malware + all goodware),
constructs the Label column from file source, and reports:

  - Numeric feature dtypes and basic descriptive stats
  - Missingness per column
  - Cardinality of string columns (candidates for feature engineering)
  - Numeric-only feature shortlist for the rubric's 27-feature requirement

Outputs:
  - notebooks/eda_outputs/feature_descriptive_stats.csv
  - notebooks/eda_outputs/missingness.csv
  - notebooks/eda_outputs/string_cardinality.csv
  - notebooks/eda_outputs/feature_shortlist.txt
"""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data" / "brazilian-malware-dataset" / "goodware-malware"
MALWARE_DIR = DATA_ROOT / "malware-by-day"
GOODWARE_CSV = DATA_ROOT / "goodware.csv"
OUT_DIR = PROJECT_ROOT / "notebooks" / "eda_outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Identifier columns to drop — not features, not labels
IDENTIFIER_COLUMNS = {"MD5", "SHA1", "Name", "Fuzzy"}

# String columns we may feature-engineer later (cardinality / count features)
STRING_FEATURE_CANDIDATES = {
    "ImportedDlls",
    "ImportedSymbols",
    "Identify",
    "FileType",
    "FormatedTimeDateStamp",
}


def load_malware_sample(months_per_year: int = 1) -> pd.DataFrame:
    """Load one month per year of malware data for a stratified time sample."""
    frames = []
    files = sorted(MALWARE_DIR.glob("*.csv"))
    if not files:
        sys.exit(f"No malware files in {MALWARE_DIR}")

    by_year_month: dict[tuple[int, int], list[Path]] = {}
    for p in files:
        if p.stat().st_size == 0:
            continue
        try:
            d = pd.to_datetime(p.stem)
        except Exception:
            continue
        by_year_month.setdefault((d.year, d.month), []).append(p)

    selected_paths: list[Path] = []
    for year in sorted({y for y, _ in by_year_month.keys()}):
        months = sorted(m for y, m in by_year_month.keys() if y == year)
        for month in months[:months_per_year]:
            selected_paths.extend(by_year_month[(year, month)])

    print(f"Loading {len(selected_paths)} malware-day files (~{months_per_year} mo/yr)")
    for p in selected_paths:
        try:
            df = pd.read_csv(p, encoding="latin-1", low_memory=False)
        except pd.errors.EmptyDataError:
            continue
        df["__sample_date"] = pd.to_datetime(p.stem)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["Label"] = 1  # malware
    print(f"Malware sample: {len(out):,} rows")
    return out


def load_goodware_sample(n_rows: int | None = None) -> pd.DataFrame:
    """Load all (or a sample of) goodware."""
    df = pd.read_csv(GOODWARE_CSV, encoding="latin-1", low_memory=False, nrows=n_rows)
    df["Label"] = 0  # goodware
    print(f"Goodware sample: {len(df):,} rows")
    return df


# Columns we EXPECT to be numeric per the schema inspection in 02_eda.py.
# Concat across many CSVs sometimes coerces these to object — we re-cast.
EXPECTED_NUMERIC = {
    "BaseOfCode", "BaseOfData", "Characteristics", "DllCharacteristics",
    "Entropy", "FileAlignment", "ImageBase", "Machine", "Magic",
    "NumberOfRvaAndSizes", "NumberOfSections", "NumberOfSymbols", "PE_TYPE",
    "PointerToSymbolTable", "Size", "SizeOfCode", "SizeOfHeaders",
    "SizeOfImage", "SizeOfInitializedData", "SizeOfOptionalHeader",
    "SizeOfUninitializedData", "TimeDateStamp",
}


def coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Force expected-numeric columns to numeric dtypes; surface coercion losses."""
    losses = {}
    for col in EXPECTED_NUMERIC & set(df.columns):
        before_null = df[col].isna().sum()
        df[col] = pd.to_numeric(df[col], errors="coerce")
        after_null = df[col].isna().sum()
        if after_null > before_null:
            losses[col] = int(after_null - before_null)
    if losses:
        print(f"Coercion losses (to_numeric→NaN): {losses}")
    return df


def numeric_descriptive_stats(df: pd.DataFrame) -> pd.DataFrame:
    numeric = df.select_dtypes(include=[np.number])
    stats = numeric.describe(percentiles=[0.05, 0.5, 0.95]).T
    stats["null_count"] = df[numeric.columns].isna().sum()
    stats["null_pct"] = (100 * stats["null_count"] / len(df)).round(2)
    out = OUT_DIR / "feature_descriptive_stats.csv"
    stats.to_csv(out)
    print(f"Wrote {out} ({len(numeric.columns)} numeric features)")
    return stats


def missingness_report(df: pd.DataFrame) -> pd.DataFrame:
    miss = pd.DataFrame({
        "dtype": df.dtypes.astype(str),
        "null_count": df.isna().sum(),
        "null_pct": (100 * df.isna().sum() / len(df)).round(2),
        "n_unique": df.nunique(dropna=True),
    })
    miss = miss.sort_values("null_pct", ascending=False)
    out = OUT_DIR / "missingness.csv"
    miss.to_csv(out)
    print(f"Wrote {out}")
    return miss


def string_cardinality(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in df.columns:
        if df[col].dtype != object:
            continue
        s = df[col].dropna().astype(str)
        rows.append({
            "column": col,
            "n_non_null": len(s),
            "n_unique": s.nunique(),
            "max_len": s.str.len().max() if len(s) else 0,
            "median_len": int(s.str.len().median()) if len(s) else 0,
        })
    sc = pd.DataFrame(rows).sort_values("n_unique", ascending=False)
    out = OUT_DIR / "string_cardinality.csv"
    sc.to_csv(out, index=False)
    print(f"Wrote {out}")
    return sc


def write_feature_shortlist(df: pd.DataFrame, stats: pd.DataFrame) -> list[str]:
    """Pick the numeric features to use for the rubric's classifier (~27 expected)."""
    numeric_cols = [
        c for c in df.select_dtypes(include=[np.number]).columns
        if c not in {"Label"}
    ]
    # Exclude near-zero variance features (would not contribute)
    nzv = []
    for c in numeric_cols:
        if df[c].nunique(dropna=True) <= 1:
            nzv.append(c)
    shortlist = [c for c in numeric_cols if c not in nzv]

    out = OUT_DIR / "feature_shortlist.txt"
    with out.open("w") as f:
        f.write("=== Numeric feature shortlist (Phase B) ===\n\n")
        f.write(
            f"Total numeric columns in shared schema: {len(numeric_cols)}\n"
            f"Near-zero-variance excluded: {nzv}\n"
            f"Shortlist count: {len(shortlist)}\n\n"
        )
        f.write("Shortlisted features:\n")
        for c in sorted(shortlist):
            mean = stats.loc[c, "mean"] if c in stats.index else "—"
            f.write(f"  - {c} (mean={mean})\n")
        f.write(
            "\n"
            "Note vs. Quantic spec: PDF specifies 27 input attributes. The Brazilian\n"
            "dataset's intersection of malware/goodware columns yields 28 numeric\n"
            "candidates after dropping identifiers (MD5/SHA1/Name) and constructing\n"
            "Label. We will reconcile to 27 by either (a) dropping TimeDateStamp\n"
            "(forgeable, ambiguous) or (b) folding it into a derived feature.\n"
        )
    print(f"Wrote {out} ({len(shortlist)} features)")
    return shortlist


def main() -> int:
    print("=== Phase B EDA: features, missingness, distributions ===\n")
    mw = load_malware_sample(months_per_year=1)
    gw = load_goodware_sample()

    # Combine on shared columns + Label
    shared = sorted((set(mw.columns) & set(gw.columns)) - IDENTIFIER_COLUMNS)
    print(f"\nShared columns (after dropping identifiers): {len(shared)}")

    combined = pd.concat([mw[shared], gw[shared]], ignore_index=True)
    print(f"Combined sample: {len(combined):,} rows "
          f"({(combined['Label'] == 1).sum():,} malware, "
          f"{(combined['Label'] == 0).sum():,} goodware)")

    print()
    combined = coerce_numeric(combined)
    stats = numeric_descriptive_stats(combined)
    miss = missingness_report(combined)
    sc = string_cardinality(combined)
    shortlist = write_feature_shortlist(combined, stats)

    print(f"\nFeature shortlist ({len(shortlist)} numeric features):")
    for c in sorted(shortlist):
        print(f"  - {c}")
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
