"""Dataset loader for the Brazilian Malware Dataset.

Combines per-day malware CSVs and the single goodware.csv into one DataFrame
with:
  - constructed `Label` column (1 = malware, 0 = goodware)
  - attached `__sample_date` (collection date for malware; NaT for goodware)
  - identifier columns dropped
  - numeric columns coerced (concat across files sometimes mixes dtypes)

Key methodological note: goodware lacks per-sample collection timestamps
(see evaluation-and-design.md §1.4). Goodware rows have NaT in
`__sample_date` and must be bootstrapped uniformly across temporal windows
by the splitter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from src import config


def _read_one_csv(path: Path, label: int, sample_date: pd.Timestamp | None) -> pd.DataFrame:
    """Read a single CSV with latin-1 fallback and attach Label + date."""
    try:
        df = pd.read_csv(path, encoding="latin-1", low_memory=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    df[config.LABEL_COL] = label
    df[config.SAMPLE_DATE_COL] = sample_date
    return df


def load_malware(
    malware_dir: Path = config.MALWARE_DIR,
    *,
    date_filter: callable | None = None,
) -> pd.DataFrame:
    """Load all malware-day CSVs (or a date-filtered subset).

    Args:
        malware_dir: directory containing YYYY-MM-DD.csv files.
        date_filter: optional predicate(pd.Timestamp) → bool. Only files
            whose basename-parsed date passes are loaded.

    Returns:
        Single concatenated DataFrame. Empty files are skipped silently.
    """
    if not malware_dir.is_dir():
        raise FileNotFoundError(
            f"Malware directory not found: {malware_dir}. "
            f"Run scripts/download_data.py first."
        )

    frames: list[pd.DataFrame] = []
    for path in sorted(malware_dir.glob("*.csv")):
        if path.stat().st_size == 0:
            continue
        try:
            sample_date = pd.to_datetime(path.stem)
        except (ValueError, TypeError):
            continue
        if date_filter is not None and not date_filter(sample_date):
            continue
        df = _read_one_csv(path, label=1, sample_date=sample_date)
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_goodware(goodware_csv: Path = config.GOODWARE_CSV) -> pd.DataFrame:
    """Load the single goodware.csv. Sample date is NaT (not available)."""
    if not goodware_csv.is_file():
        raise FileNotFoundError(
            f"Goodware CSV not found: {goodware_csv}. "
            f"Run scripts/download_data.py first."
        )
    return _read_one_csv(goodware_csv, label=0, sample_date=pd.NaT)


def _drop_identifiers_and_nzv(df: pd.DataFrame) -> pd.DataFrame:
    """Remove identifier columns and near-zero-variance constants."""
    drop_cols = [
        c for c in (*config.IDENTIFIER_COLUMNS, *config.NEAR_ZERO_VARIANCE_COLUMNS)
        if c in df.columns
    ]
    return df.drop(columns=drop_cols)


def _coerce_numeric(df: pd.DataFrame, numeric_cols: Iterable[str]) -> pd.DataFrame:
    """Force expected-numeric columns to numeric. Concat across CSVs sometimes
    coerces them to object when individual files have inconsistent types."""
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def load_combined(
    *,
    malware_dir: Path = config.MALWARE_DIR,
    goodware_csv: Path = config.GOODWARE_CSV,
    date_filter: callable | None = None,
) -> pd.DataFrame:
    """Load malware + goodware, combine, drop identifiers/NZV, coerce numerics.

    Returned DataFrame has:
      - all 27 shared schema columns (raw)
      - `Label` column (1 = malware, 0 = goodware)
      - `__sample_date` (Timestamp for malware, NaT for goodware)

    Args:
        date_filter: applied to malware only (goodware has no per-sample date).

    Returns:
        Combined DataFrame ready for feature engineering.
    """
    malware = load_malware(malware_dir, date_filter=date_filter)
    goodware = load_goodware(goodware_csv)

    # Shared columns only (intersection of malware and goodware schemas)
    shared = sorted((set(malware.columns) & set(goodware.columns)))
    combined = pd.concat(
        [malware[shared], goodware[shared]],
        ignore_index=True,
    )

    combined = _drop_identifiers_and_nzv(combined)
    combined = _coerce_numeric(combined, config.RAW_NUMERIC_FEATURES)
    return combined
