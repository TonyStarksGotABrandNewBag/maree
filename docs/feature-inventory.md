# Feature inventory — Brazilian Malware Dataset

This document maps the dataset's raw columns to the features M.A.R.E.E. consumes,
and reconciles the dataset's actual schema against the Quantic project spec
("27 input attributes + Label").

## Raw schema

The dataset is split across two file types:

- **`malware-by-day/YYYY-MM-DD.csv`** — 31 columns per file, one file per day from 2013-01-01 to 2020-11-29 (2,797 files; 1,501 are empty placeholders).
- **`goodware.csv`** — 29 columns, 21,116 rows.

Neither file contains an explicit `Label` column. Class is encoded by file location:
malware lives in `malware-by-day/`, goodware lives in `goodware.csv`. We construct
the `Label` column ourselves: `1` for malware, `0` for goodware.

## Shared columns (27 — matches Quantic spec exactly)

After dropping non-feature identifier columns (`MD5`, `SHA1`, `Name`, `Fuzzy`),
the intersection of the two file schemas is **27 columns**, which aligns
precisely with the Quantic PDF's "27 input attributes" specification.

### Numeric (22)

| Column | Dtype | Cardinality (sample) | Notes |
|---|---|---|---|
| `BaseOfCode` | int64 | 310 | PE header field |
| `BaseOfData` | int64 | 1,108 | PE header field |
| `Characteristics` | int64 | 53 | PE Characteristics flags |
| `DllCharacteristics` | int64 | 42 | DLL Characteristics flags |
| `Entropy` | float64 | 23,177 | File entropy (Shannon) |
| `FileAlignment` | int64 | 6 | Section alignment in file |
| `ImageBase` | int64 | 3,363 | Preferred load address |
| `Machine` | int64 | 3 | Target CPU architecture |
| `Magic` | int64 | **1** | **Constant — drop (NZV)** |
| `NumberOfRvaAndSizes` | int64 | 5 | Optional header data dirs count |
| `NumberOfSections` | int64 | 19 | Number of PE sections |
| `NumberOfSymbols` | int64 | 40 | Symbol table count |
| `PE_TYPE` | int64 | **1** | **Constant — drop (NZV)** |
| `PointerToSymbolTable` | int64 | 55 | Symbol table offset |
| `Size` | int64 | 11,785 | Total file size in bytes |
| `SizeOfCode` | int64 | 2,945 | Code section size |
| `SizeOfHeaders` | int64 | 11 | Headers size |
| `SizeOfImage` | int64 | 1,787 | Image size in memory |
| `SizeOfInitializedData` | int64 | 2,360 | Initialized data size |
| `SizeOfOptionalHeader` | int64 | **1** | **Constant — drop (NZV)** |
| `SizeOfUninitializedData` | int64 | 370 | Uninitialized data size |
| `TimeDateStamp` | int64 | 12,815 | PE-embedded timestamp (Unix epoch). **Forgeable; treat with care.** |

### Strings (4) — feature-engineered downstream

| Column | Dtype | Cardinality (sample) | Engineering plan |
|---|---|---|---|
| `FormatedTimeDateStamp` | str | 12,815 | Parsed form of `TimeDateStamp`. Used for temporal positioning of goodware (with forgeability caveat below). |
| `Identify` | str | 184 (41% null) | Detector signatures (e.g., "UPX", "ACProtect"). Engineer as: `is_packed` binary, signature count, top-K signature one-hot. |
| `ImportedDlls` | str | 7,836 | List of imported DLLs. Engineer as: count, top-K DLL one-hot (KERNEL32, USER32, etc.). |
| `ImportedSymbols` | str | 11,421 | List of imported function symbols. Engineer as: count, dangerous-API flags (e.g., `VirtualAlloc`, `LoadLibraryA`, `WinExec`). |

### Identifier columns (dropped, not features)

`MD5`, `SHA1`, `Name`, `Fuzzy` — sample identifiers. Used for deduplication and traceability, never as model inputs.

## Feature shortlist for modeling

After dropping the 3 near-zero-variance numeric columns (`Magic`, `PE_TYPE`, `SizeOfOptionalHeader`), the **19 raw numeric features** form the baseline feature set.

We then add **engineered features** from string columns to bring the total to 27 (matching the Quantic spec target):

| Engineered feature | Source | Definition |
|---|---|---|
| `n_imported_dlls` | `ImportedDlls` | Count of DLLs in the list |
| `n_imported_symbols` | `ImportedSymbols` | Count of imported symbols |
| `identify_is_packed` | `Identify` | Binary: contains "UPX"/"ACProtect"/etc. |
| `identify_signature_count` | `Identify` | Number of detected packers/protectors |
| `formatted_timedatestamp_year` | `FormatedTimeDateStamp` | Year extracted from PE timestamp (informational) |
| `imports_winexec_or_loadlib` | `ImportedSymbols` | Binary: imports `WinExec`, `LoadLibraryA`, `VirtualAlloc`, `CreateProcessA`, etc. |
| `time_alignment_anomaly` | `TimeDateStamp` vs `FormatedTimeDateStamp` | Binary: unix timestamp doesn't decode to plausible date |
| `dll_count_anomaly` | `n_imported_dlls` | Binary: 0 imports OR > 100 imports (both unusual) |

19 raw + 8 engineered = **27 features**. Matches the Quantic spec.

## Critical methodological note: temporal positioning

For Pendlebury-style temporal evaluation, every sample needs a known collection date.

- **Malware**: collection date = file basename (e.g., `2013-01-02.csv` → all rows collected 2013-01-02). High-confidence per-sample timestamp.
- **Goodware**: no per-sample collection date. The only available temporal signal is `FormatedTimeDateStamp`, the PE-embedded compile timestamp. We confirmed this field is **unreliable** in this dataset — values range from 1969-12-31 to 2100-02-26, well outside any plausible collection window. PE timestamps are routinely forged or zeroed.

**Decision**: for the temporal evaluation experiment, we treat goodware as **temporally distributed in proportion to its sampling**, since a single trustworthy collection date does not exist per goodware sample. Goodware is bootstrapped uniformly across the train/test windows. This is the standard treatment in the Pendlebury and CADE literature when one class lacks per-sample timestamps.

We will document this decision and its implications explicitly in `evaluation-and-design.md`.
