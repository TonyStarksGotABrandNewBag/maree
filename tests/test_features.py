"""Unit tests for src.features — string-column feature engineering."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src import config
from src.features import (
    PACKER_PATTERNS,
    DANGEROUS_API_NAMES,
    engineer_string_features,
    _safe_parse_list,
    _identify_is_packed,
    _imports_dangerous_api,
    _time_alignment_anomaly,
    _dll_count_anomaly,
)


class TestSafeParseList:
    def test_parses_python_list_repr(self):
        assert _safe_parse_list("['a', 'b', 'c']") == ["a", "b", "c"]

    def test_handles_empty_string(self):
        assert _safe_parse_list("") == []

    def test_handles_none(self):
        assert _safe_parse_list(None) == []

    def test_handles_nan(self):
        assert _safe_parse_list(float("nan")) == []

    def test_handles_malformed_returns_empty(self):
        # Garbage input must not raise
        assert _safe_parse_list("[unclosed") == []

    def test_handles_pipe_separated_fallback(self):
        # Some rows have non-bracket separator forms
        assert _safe_parse_list("a|b|c") == ["a", "b", "c"]


class TestIdentifyIsPacked:
    def test_detects_upx(self):
        assert _identify_is_packed("['UPX v0.89.6 - v1.02']") == 1

    def test_detects_acprotect(self):
        assert _identify_is_packed("ACProtect 1.3x DLL") == 1

    def test_returns_zero_for_unknown(self):
        assert _identify_is_packed("Plain executable") == 0

    def test_returns_zero_for_none(self):
        assert _identify_is_packed(None) == 0

    def test_all_known_packers_recognized(self):
        for p in PACKER_PATTERNS:
            assert _identify_is_packed(f"signature: {p}") == 1, f"Failed for {p!r}"


class TestImportsDangerousApi:
    def test_detects_loadlibrary(self):
        assert _imports_dangerous_api("['LoadLibraryA', 'GetProcAddress']") == 1

    def test_detects_winexec(self):
        assert _imports_dangerous_api("['WinExec', 'printf']") == 1

    def test_returns_zero_for_safe_imports(self):
        assert _imports_dangerous_api("['printf', 'malloc', 'free']") == 0

    def test_returns_zero_for_empty(self):
        assert _imports_dangerous_api("[]") == 0


class TestTimeAlignmentAnomaly:
    def test_plausible_year_is_normal(self):
        assert _time_alignment_anomaly(2014.0) == 0

    def test_implausibly_early_is_anomalous(self):
        assert _time_alignment_anomaly(1969.0) == 1

    def test_implausibly_late_is_anomalous(self):
        assert _time_alignment_anomaly(2100.0) == 1

    def test_nan_is_anomalous(self):
        assert _time_alignment_anomaly(float("nan")) == 1


class TestDllCountAnomaly:
    def test_zero_imports_is_anomalous(self):
        assert _dll_count_anomaly(0) == 1

    def test_normal_count_is_not_anomalous(self):
        assert _dll_count_anomaly(5) == 0
        assert _dll_count_anomaly(50) == 0

    def test_excessive_imports_is_anomalous(self):
        assert _dll_count_anomaly(150) == 1


class TestEngineerStringFeatures:
    def test_produces_all_8_engineered_columns(self, tiny_combined: pd.DataFrame):
        out = engineer_string_features(tiny_combined)
        for col in config.ENGINEERED_FEATURES:
            assert col in out.columns, f"Missing engineered feature: {col}"

    def test_all_engineered_are_numeric(self, tiny_combined: pd.DataFrame):
        out = engineer_string_features(tiny_combined)
        for col in config.ENGINEERED_FEATURES:
            # year may be NaN for unparseable timestamps
            non_null = out[col].dropna()
            assert pd.api.types.is_numeric_dtype(non_null), \
                f"{col} not numeric: dtype={out[col].dtype}"

    def test_does_not_mutate_input(self, tiny_combined: pd.DataFrame):
        before_cols = list(tiny_combined.columns)
        _ = engineer_string_features(tiny_combined)
        assert list(tiny_combined.columns) == before_cols

    def test_handles_missing_source_columns_gracefully(self):
        df = pd.DataFrame({"BaseOfCode": [1, 2, 3]})  # no string sources
        out = engineer_string_features(df)
        for col in config.ENGINEERED_FEATURES:
            assert col in out.columns
