from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd


def clean_for_json(value: Any) -> Any:
    """Convert Pandas, NumPy, date, and datetime values into JSON-safe values."""

    if isinstance(value, dict):
        return {
            str(key): clean_for_json(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [clean_for_json(item) for item in value]

    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass

    return value
