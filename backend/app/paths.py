"""Single source of truth for where data lives.

Dev defaults follow the repo layout; in a container point DATA_DIR / WEIGHT_JSON /
DATABASE_URL at a volume so data survives image rebuilds.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[2]

DATA_DIR: Path = Path(os.environ.get("DATA_DIR")
                      or REPO_ROOT / "portfolio_optim" / "data").resolve()

WEIGHT_JSON: Path = Path(os.environ.get("WEIGHT_JSON")
                         or REPO_ROOT / "weight.json").resolve()

INDEX_FTSE_CSV: Path = DATA_DIR / "index_ftse.csv"
INDEX_VNINDEX_CSV: Path = DATA_DIR / "index_vnindex.csv"
VNINDEX_RAW_CSV: Path = DATA_DIR / "_VNINDEX_raw.csv"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
