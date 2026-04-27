"""First-look data inspection.

Loads one daily CSV and one batch (first 30 days) from the Brazilian Malware
Dataset, reports column inventory, sample counts, and class balance over time.

Run as a script (`python notebooks/01_data_load.py`) or paste cell-by-cell into
Jupyter. We keep early notebooks as .py for cleaner diffs; convert to .ipynb
for Phase B (Week 1) EDA.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DAILY_DIR = PROJECT_ROOT / "data" / "brazilian-malware-dataset" / "goodware-malware" / "malware-by-day"
GOODWARE_CSV = PROJECT_ROOT / "data" / "brazilian-malware-dataset" / "goodware-malware" / "goodware.csv"


def inspect_one_day(date_str: str = "2013-01-01") -> pd.DataFrame:
    path = DAILY_DIR / f"{date_str}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python scripts/download_data.py` first."
        )

    df = pd.read_csv(path)
    print(f"== {date_str} ==")
    print(f"Rows: {len(df):,}")
    print(f"Columns ({len(df.columns)}): {list(df.columns)}")
    print(f"Dtypes:\n{df.dtypes}")
    if "Label" in df.columns:
        print(f"Class balance:\n{df['Label'].value_counts()}")
    return df


def inspect_first_n_days(n: int = 30) -> pd.DataFrame:
    files = sorted(DAILY_DIR.glob("*.csv"))[:n]
    if not files:
        raise FileNotFoundError(
            f"No CSVs in {DAILY_DIR}. Run `python scripts/download_data.py` first."
        )

    frames = []
    for path in files:
        date = path.stem
        df = pd.read_csv(path)
        df["__source_date"] = pd.to_datetime(date)
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    print(f"\n== First {n} days combined ==")
    print(f"Total rows: {len(combined):,}")
    print(f"Date range: {combined['__source_date'].min().date()} → {combined['__source_date'].max().date()}")
    if "Label" in combined.columns:
        print(f"Overall class balance:\n{combined['Label'].value_counts()}")
        per_day = combined.groupby([combined["__source_date"].dt.date, "Label"]).size().unstack(fill_value=0)
        print(f"\nPer-day breakdown (first 10 rows):\n{per_day.head(10)}")
    return combined


def inspect_goodware() -> pd.DataFrame | None:
    if not GOODWARE_CSV.exists():
        print(f"Goodware CSV not found at {GOODWARE_CSV}")
        return None
    df = pd.read_csv(GOODWARE_CSV)
    print(f"\n== Goodware ==")
    print(f"Rows: {len(df):,}")
    print(f"Columns ({len(df.columns)}): {list(df.columns)}")
    return df


if __name__ == "__main__":
    inspect_one_day("2013-01-01")
    inspect_first_n_days(30)
    inspect_goodware()
