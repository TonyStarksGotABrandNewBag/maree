"""Engineered features from string columns.

The Brazilian dataset has 4 string columns we feature-engineer to add 8
numeric features. Combined with the 19 retained raw numeric columns, this
yields the 27 features matching the Quantic PDF specification.

Engineered feature contract (must match config.ENGINEERED_FEATURES exactly):

  - n_imported_dlls            (int)   count of DLLs in ImportedDlls
  - n_imported_symbols         (int)   count of symbols in ImportedSymbols
  - identify_is_packed         (0/1)   any packer signature in Identify
  - identify_signature_count   (int)   number of signatures in Identify
  - formatted_timedatestamp_year (int) year parsed from FormatedTimeDateStamp
  - imports_dangerous_api      (0/1)   imports any of the dangerous-API set
  - time_alignment_anomaly     (0/1)   PE timestamp decodes to implausible date
  - dll_count_anomaly          (0/1)   import count is 0 or > 100
"""

from __future__ import annotations

import ast
import re

import numpy as np
import pandas as pd

# Substrings flagged as packer/protector indicators in the `Identify` field.
PACKER_PATTERNS = (
    "UPX", "ACProtect", "ASPack", "PECompact", "MEW", "Themida",
    "VMProtect", "Armadillo", "FSG", "PEX", "Yoda", "Petite",
    "Enigma", "Obsidium", "MoleBox", "PELock",
)

# Imported function names commonly associated with malware capability:
# memory injection, code execution, process manipulation. Presence is not
# proof of malice, but absence is informative.
DANGEROUS_API_NAMES = frozenset({
    "WinExec", "CreateProcessA", "CreateProcessW",
    "VirtualAlloc", "VirtualAllocEx", "VirtualProtect",
    "WriteProcessMemory", "ReadProcessMemory",
    "LoadLibraryA", "LoadLibraryW", "LoadLibraryExA", "LoadLibraryExW",
    "GetProcAddress",
    "CreateRemoteThread", "NtCreateThreadEx",
    "OpenProcess", "TerminateProcess",
    "RegSetValueExA", "RegSetValueExW",
    "InternetOpenA", "InternetOpenUrlA", "URLDownloadToFileA",
    "CreateFileA", "CreateFileW",  # filesystem manipulation
    "ShellExecuteA", "ShellExecuteW",
    "CryptEncrypt", "CryptDecrypt",  # ransomware indicator
})

# Reasonable plausibility window for a PE compile timestamp.
PLAUSIBLE_PE_YEAR_MIN = 1990
PLAUSIBLE_PE_YEAR_MAX = 2030


def _safe_parse_list(s: object) -> list:
    """Try to parse a string-encoded Python list; return [] on any failure.

    The dataset stores ImportedDlls / ImportedSymbols as Python list reprs:
    "['kernel32.dll', 'user32.dll']". A few rows have malformed entries.
    """
    if not isinstance(s, str) or not s:
        return []
    s = s.strip()
    if not s.startswith("["):
        # Some rows have been seen with pipe- or comma-separated lists
        return [tok.strip().strip("'\"") for tok in re.split(r"[|,]", s) if tok.strip()]
    try:
        parsed = ast.literal_eval(s)
        return list(parsed) if isinstance(parsed, list | tuple) else []
    except (ValueError, SyntaxError):
        return []


def _count_imported_dlls(s: object) -> int:
    return len(_safe_parse_list(s))


def _count_imported_symbols(s: object) -> int:
    return len(_safe_parse_list(s))


def _identify_is_packed(s: object) -> int:
    if not isinstance(s, str):
        return 0
    return int(any(p in s for p in PACKER_PATTERNS))


def _identify_signature_count(s: object) -> int:
    """Count the comma-or-bracket-separated signatures in Identify."""
    if not isinstance(s, str) or not s:
        return 0
    parsed = _safe_parse_list(s)
    if parsed:
        # Identify can be a list of lists of signature strings — flatten.
        flat = []
        for item in parsed:
            if isinstance(item, list):
                flat.extend(item)
            else:
                flat.append(item)
        return len(flat)
    return s.count(",") + 1


def _parse_timestamp_year(s: object) -> float:
    if not isinstance(s, str) or not s:
        return np.nan
    try:
        return pd.to_datetime(s).year
    except (ValueError, TypeError):
        return np.nan


def _imports_dangerous_api(s: object) -> int:
    items = _safe_parse_list(s)
    return int(any(name in DANGEROUS_API_NAMES for name in items))


def _time_alignment_anomaly(year_value: float) -> int:
    """1 if the PE timestamp year is implausible (forged/zeroed) or NaN."""
    if pd.isna(year_value):
        return 1
    return int(not (PLAUSIBLE_PE_YEAR_MIN <= year_value <= PLAUSIBLE_PE_YEAR_MAX))


def _dll_count_anomaly(n_dlls: int) -> int:
    """1 if import count is 0 (statically linked / packed) or > 100 (unusual)."""
    return int(n_dlls == 0 or n_dlls > 100)


def engineer_string_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add the 8 engineered features to a DataFrame in-place style (returns new).

    Source columns are read by name. Missing source columns produce all-zero
    or all-NaN engineered features, with a warning-equivalent that the
    column was missing (we do not raise — robust to schema variation).
    """
    out = df.copy()

    # Counts (integer)
    if "ImportedDlls" in out.columns:
        out["n_imported_dlls"] = out["ImportedDlls"].apply(_count_imported_dlls)
    else:
        out["n_imported_dlls"] = 0

    if "ImportedSymbols" in out.columns:
        out["n_imported_symbols"] = out["ImportedSymbols"].apply(_count_imported_symbols)
    else:
        out["n_imported_symbols"] = 0

    # Identify-derived
    if "Identify" in out.columns:
        out["identify_is_packed"] = out["Identify"].apply(_identify_is_packed)
        out["identify_signature_count"] = out["Identify"].apply(_identify_signature_count)
    else:
        out["identify_is_packed"] = 0
        out["identify_signature_count"] = 0

    # Timestamp year
    if "FormatedTimeDateStamp" in out.columns:
        out["formatted_timedatestamp_year"] = out["FormatedTimeDateStamp"].apply(_parse_timestamp_year)
    else:
        out["formatted_timedatestamp_year"] = np.nan

    # Dangerous API
    if "ImportedSymbols" in out.columns:
        out["imports_dangerous_api"] = out["ImportedSymbols"].apply(_imports_dangerous_api)
    else:
        out["imports_dangerous_api"] = 0

    # Anomalies
    out["time_alignment_anomaly"] = out["formatted_timedatestamp_year"].apply(_time_alignment_anomaly)
    out["dll_count_anomaly"] = out["n_imported_dlls"].apply(_dll_count_anomaly)

    return out
