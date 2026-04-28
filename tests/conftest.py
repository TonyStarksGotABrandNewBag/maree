"""Shared pytest fixtures.

Synthetic-fixture-driven tests so they run fast and don't require the
full dataset on disk. Real-data integration tests live in
tests/test_real_data_pipeline.py and are skipped if the dataset isn't
present.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src import config


@pytest.fixture()
def tiny_combined() -> pd.DataFrame:
    """A 50-row synthetic DataFrame mimicking the loader's combined output.

    Has all 27 raw schema columns (after identifier/NZV drop), Label,
    and __sample_date populated for malware.
    """
    n_mw = 30
    n_gw = 20
    rng = np.random.default_rng(0)

    def _row(i: int, label: int, date: pd.Timestamp | None) -> dict:
        return {
            "BaseOfCode": int(rng.integers(0, 10**6)),
            "BaseOfData": int(rng.integers(0, 10**6)),
            "Characteristics": int(rng.integers(0, 50000)),
            "DllCharacteristics": int(rng.integers(0, 60000)),
            "Entropy": float(rng.uniform(0, 8)),
            "FileAlignment": int(rng.choice([32, 512, 4096])),
            "ImageBase": int(rng.integers(65536, 3 * 10**9)),
            "Machine": int(rng.choice([332, 452, 34404])),
            "NumberOfRvaAndSizes": int(rng.integers(0, 20)),
            "NumberOfSections": int(rng.integers(1, 22)),
            "NumberOfSymbols": int(rng.integers(0, 100)),
            "PointerToSymbolTable": int(rng.integers(0, 100)),
            "Size": int(rng.integers(2560, 10**8)),
            "SizeOfCode": int(rng.integers(0, 10**6)),
            "SizeOfHeaders": int(rng.choice([512, 1024, 4096])),
            "SizeOfImage": int(rng.integers(3840, 10**7)),
            "SizeOfInitializedData": int(rng.integers(0, 10**6)),
            "SizeOfUninitializedData": int(rng.integers(0, 10**6)),
            "TimeDateStamp": int(rng.integers(10**9, 1.6 * 10**9)),
            "ImportedDlls": "['KERNEL32.DLL', 'USER32.DLL']" if i % 2 else "['ADVAPI32.DLL']",
            "ImportedSymbols": "['LoadLibraryA', 'VirtualAlloc']" if i % 3 else "['printf', 'malloc']",
            "Identify": "['UPX v0.89.6']" if i % 5 else "[]",
            "FormatedTimeDateStamp": "2014-06-15 12:00:00" if i % 4 else "1970-01-01 00:00:00",
            config.LABEL_COL: label,
            config.SAMPLE_DATE_COL: date,
        }

    rows = []
    base_date = pd.Timestamp("2013-01-01")
    for i in range(n_mw):
        rows.append(_row(i, label=1, date=base_date + pd.Timedelta(days=i * 10)))
    for i in range(n_gw):
        rows.append(_row(n_mw + i, label=0, date=pd.NaT))
    df = pd.DataFrame(rows)
    # Shuffle so tests that slice [:k] get both classes
    return df.sample(frac=1.0, random_state=0).reset_index(drop=True)


@pytest.fixture()
def real_data_available() -> bool:
    """True iff the Brazilian Malware Dataset has been downloaded."""
    return config.MALWARE_DIR.is_dir() and config.GOODWARE_CSV.is_file()
