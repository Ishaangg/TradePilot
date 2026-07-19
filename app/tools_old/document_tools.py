from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def clean_for_json(value: Any) -> Any:
    """Convert Pandas/NumPy values into valid JSON-compatible values."""

    if isinstance(value, dict):
        return {
            str(key): clean_for_json(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [clean_for_json(item) for item in value]

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    return value


def get_shipment_documents(shipment_id: str) -> dict:
    """Return document records and identify missing documents."""

    documents_path = DATA_DIR / "documents.csv"

    if not documents_path.exists():
        return {
            "success": False,
            "error": f"Dataset not found: {documents_path}",
        }

    dataframe = pd.read_csv(
        documents_path,
        dtype={"shipment_id": str},
        encoding="utf-8-sig",
    )

    dataframe["shipment_id"] = (
        dataframe["shipment_id"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    normalized_id = shipment_id.strip().upper()

    matches = dataframe[
        dataframe["shipment_id"] == normalized_id
    ].copy()

    if matches.empty:
        return {
            "success": True,
            "document_count": 0,
            "documents": [],
            "missing_documents": [],
            "warning": "No document records exist for this shipment.",
        }

    missing = matches[
        matches["document_status"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
        == "missing"
    ]

    result = {
        "success": True,
        "document_count": len(matches),
        "documents": matches.to_dict(orient="records"),
        "missing_documents": missing["document_type"]
        .dropna()
        .astype(str)
        .tolist(),
    }

    return clean_for_json(result)