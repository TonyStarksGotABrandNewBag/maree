"""Global configuration for M.A.R.E.E.

Single source of truth for paths, random seeds, feature names, and split
parameters. Everything in src/ should import constants from here rather than
hardcoding them, so reproducibility is anchored to one file.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = PROJECT_ROOT / "data" / "brazilian-malware-dataset" / "goodware-malware"
MALWARE_DIR = DATA_ROOT / "malware-by-day"
GOODWARE_CSV = DATA_ROOT / "goodware.csv"

# ---------------------------------------------------------------------------
# Random seeds — every stochastic step in the pipeline reads from here
# ---------------------------------------------------------------------------
GLOBAL_SEED = 42  # the answer; also the Quantic-rubric reproducibility anchor
SPLIT_SEED = 42
CV_SEED = 42

# ---------------------------------------------------------------------------
# Schema — derived from Phase B EDA (see docs/feature-inventory.md)
# ---------------------------------------------------------------------------
LABEL_COL = "Label"
SAMPLE_DATE_COL = "__sample_date"  # collection date attached at load time

# Identifier columns: present in raw files, never used as features.
IDENTIFIER_COLUMNS = ("MD5", "SHA1", "Name", "Fuzzy")

# Near-zero-variance constants in this dataset (Magic, PE_TYPE,
# SizeOfOptionalHeader were single-valued in Phase B).
NEAR_ZERO_VARIANCE_COLUMNS = ("Magic", "PE_TYPE", "SizeOfOptionalHeader")

# Raw numeric features after dropping NZV. 19 columns.
RAW_NUMERIC_FEATURES = (
    "BaseOfCode",
    "BaseOfData",
    "Characteristics",
    "DllCharacteristics",
    "Entropy",
    "FileAlignment",
    "ImageBase",
    "Machine",
    "NumberOfRvaAndSizes",
    "NumberOfSections",
    "NumberOfSymbols",
    "PointerToSymbolTable",
    "Size",
    "SizeOfCode",
    "SizeOfHeaders",
    "SizeOfImage",
    "SizeOfInitializedData",
    "SizeOfUninitializedData",
    "TimeDateStamp",
)

# String columns we feature-engineer in src/features.py
STRING_FEATURE_SOURCES = (
    "ImportedDlls",
    "ImportedSymbols",
    "Identify",
    "FormatedTimeDateStamp",
)

# Engineered features produced by src/features.py — names must match the
# columns engineer_string_features() returns. 8 columns.
ENGINEERED_FEATURES = (
    "n_imported_dlls",
    "n_imported_symbols",
    "identify_is_packed",
    "identify_signature_count",
    "formatted_timedatestamp_year",
    "imports_dangerous_api",
    "time_alignment_anomaly",
    "dll_count_anomaly",
)

# Final feature list: 19 raw numeric + 8 engineered = 27 features.
# Matches the Quantic PDF's "27 input attributes" specification.
FEATURE_COLUMNS = RAW_NUMERIC_FEATURES + ENGINEERED_FEATURES

# ---------------------------------------------------------------------------
# Split parameters
# ---------------------------------------------------------------------------
RANDOM_TEST_FRACTION = 0.20  # rubric: 80/20 stratified hold-out
TEMPORAL_TEST_FRACTION = 0.20  # newest 20% by sample-date for temporal hold-out
CV_FOLDS = 10  # rubric: 10-fold stratified CV
