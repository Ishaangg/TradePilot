from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def read_csv(filename: str, **kwargs: Any) -> pd.DataFrame:
    """Read one project CSV using stable defaults."""

    path = DATA_DIR / filename

    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    return pd.read_csv(
        path,
        encoding="utf-8-sig",
        keep_default_na=True,
        **kwargs,
    )


def normalize_text(value: Any) -> str:
    """Normalize identifiers and text for case-insensitive comparisons."""

    if value is None:
        return ""

    return str(value).strip().upper()
