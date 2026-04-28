"""Unit tests for src.data.loader.

Real-data tests are gated on the dataset being present (skipped in CI by
default). Synthetic tests cover the helper functions and error paths.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src import config
from src.data import loader


class TestErrorPaths:
    def test_load_malware_raises_when_dir_missing(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="Malware directory"):
            loader.load_malware(malware_dir=tmp_path / "does-not-exist")

    def test_load_goodware_raises_when_file_missing(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="Goodware CSV"):
            loader.load_goodware(goodware_csv=tmp_path / "does-not-exist.csv")


class TestSyntheticLoad:
    """Build a tiny dataset on disk and round-trip through the loader."""

    def test_loader_attaches_label_and_date(self, tmp_path: Path):
        # Create one fake malware-day CSV and one fake goodware CSV
        mw_dir = tmp_path / "malware-by-day"
        mw_dir.mkdir()
        mw_path = mw_dir / "2014-06-15.csv"
        mw_path.write_text(
            "BaseOfCode,Size,MD5,SHA1,Name,Magic,PE_TYPE,SizeOfOptionalHeader\n"
            "4096,12345,abc,def,evil.exe,267,267,224\n"
            "8192,67890,abc2,def2,evil2.exe,267,267,224\n"
        )
        gw_path = tmp_path / "goodware.csv"
        gw_path.write_text(
            "BaseOfCode,Size,MD5,SHA1,Name,Magic,PE_TYPE,SizeOfOptionalHeader\n"
            "4096,11111,ggg,ghh,good.exe,267,267,224\n"
        )

        combined = loader.load_combined(
            malware_dir=mw_dir,
            goodware_csv=gw_path,
        )

        # Label column constructed
        assert config.LABEL_COL in combined.columns
        assert (combined[config.LABEL_COL] == 1).sum() == 2
        assert (combined[config.LABEL_COL] == 0).sum() == 1

        # Sample date attached for malware, NaT for goodware
        mw_rows = combined[combined[config.LABEL_COL] == 1]
        gw_rows = combined[combined[config.LABEL_COL] == 0]
        assert (mw_rows[config.SAMPLE_DATE_COL] == pd.Timestamp("2014-06-15")).all()
        assert gw_rows[config.SAMPLE_DATE_COL].isna().all()

        # Identifier columns dropped
        for ident in config.IDENTIFIER_COLUMNS:
            assert ident not in combined.columns
        # NZV columns dropped
        for nzv in config.NEAR_ZERO_VARIANCE_COLUMNS:
            assert nzv not in combined.columns

    def test_loader_skips_empty_files(self, tmp_path: Path):
        mw_dir = tmp_path / "malware-by-day"
        mw_dir.mkdir()
        # One empty file, one with data
        (mw_dir / "2013-01-01.csv").write_text("")
        (mw_dir / "2013-01-02.csv").write_text(
            "BaseOfCode,Size\n4096,1234\n"
        )
        df = loader.load_malware(malware_dir=mw_dir)
        assert len(df) == 1
        assert df[config.SAMPLE_DATE_COL].iloc[0] == pd.Timestamp("2013-01-02")


# Real-data smoke test (skipped when dataset isn't on disk)
@pytest.mark.skipif(
    not (config.MALWARE_DIR.is_dir() and config.GOODWARE_CSV.is_file()),
    reason="Brazilian Malware Dataset not downloaded — run scripts/download_data.py",
)
class TestRealDataLoad:
    def test_real_combined_has_expected_class_balance(self):
        # Load a small slice — first month of malware + all goodware
        cutoff = pd.Timestamp("2013-02-01")
        df = loader.load_combined(date_filter=lambda d: d < cutoff)
        n_malware = int((df[config.LABEL_COL] == 1).sum())
        n_goodware = int((df[config.LABEL_COL] == 0).sum())
        assert n_malware > 0
        assert n_goodware > 0
        # Goodware corpus is ~21k regardless of malware filter
        assert n_goodware == 21_116
