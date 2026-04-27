"""Download the Brazilian Malware Dataset (Ceschin et al., 2018).

Source: https://github.com/fabriciojoc/brazilian-malware-dataset

Cloned in full so we have the per-day CSVs in goodware-malware/malware-by-day/
plus the goodware.csv. The repo is ~tens of MB; a clone is the simplest
reliable acquisition.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/fabriciojoc/brazilian-malware-dataset.git"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "brazilian-malware-dataset"


def main() -> int:
    if DATA_DIR.exists():
        print(f"Dataset already present at {DATA_DIR}")
        print("Delete the directory and re-run if you want a fresh clone.")
        return 0

    DATA_DIR.parent.mkdir(parents=True, exist_ok=True)

    print(f"Cloning {REPO_URL} → {DATA_DIR}")
    result = subprocess.run(
        ["git", "clone", "--depth=1", REPO_URL, str(DATA_DIR)],
        check=False,
    )
    if result.returncode != 0:
        print("Clone failed.", file=sys.stderr)
        return result.returncode

    daily_dir = DATA_DIR / "goodware-malware" / "malware-by-day"
    if not daily_dir.is_dir():
        print(f"Expected directory missing: {daily_dir}", file=sys.stderr)
        return 1

    daily_files = sorted(daily_dir.glob("*.csv"))
    print(f"Found {len(daily_files):,} per-day CSV files in {daily_dir}")
    if daily_files:
        print(f"  First: {daily_files[0].name}")
        print(f"  Last:  {daily_files[-1].name}")

    goodware_csv = DATA_DIR / "goodware-malware" / "goodware.csv"
    if goodware_csv.exists():
        size_mb = goodware_csv.stat().st_size / (1024 * 1024)
        print(f"Goodware CSV: {goodware_csv} ({size_mb:.1f} MB)")

    print("\nDataset ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
