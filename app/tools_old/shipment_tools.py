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


def get_shipment(shipment_id: str) -> dict:
    """Return one shipment by shipment ID."""

    shipments_path = DATA_DIR / "shipments.csv"

    if not shipments_path.exists():
        return {
            "success": False,
            "error": f"Dataset not found: {shipments_path}",
        }

    dataframe = pd.read_csv(
        shipments_path,
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
    ]

    if matches.empty:
        return {
            "success": False,
            "error": (
                f"Shipment {normalized_id} was not found. "
                f"Loaded {len(dataframe)} shipments."
            ),
        }

    return clean_for_json({
        "success": True,
        "shipment": matches.iloc[0].to_dict(),
    })


def get_shipment_items(shipment_id: str) -> dict:
    """Return all line items belonging to a shipment."""

    items_path = DATA_DIR / "shipment_items.csv"

    if not items_path.exists():
        return {
            "success": False,
            "error": f"Dataset not found: {items_path}",
        }

    dataframe = pd.read_csv(
        items_path,
        dtype={
            "shipment_id": str,
            "hs_code": str,
        },
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
            "success": False,
            "error": f"No line items found for {normalized_id}.",
        }

    return clean_for_json({
        "success": True,
        "item_count": len(matches),
        "items": matches.to_dict(orient="records"),
    })