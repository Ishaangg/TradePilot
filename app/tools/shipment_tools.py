from __future__ import annotations

from app.tools.data_access import normalize_text, read_csv
from app.utils.serialization import clean_for_json


def get_shipment(shipment_id: str) -> dict:
    """Return one raw shipment record by shipment ID."""

    normalized_id = normalize_text(shipment_id)

    try:
        shipments = read_csv(
            "shipments.csv",
            dtype={
                "shipment_id": str,
                "exporter_id": str,
                "buyer_id": str,
                "destination_market": str,
            },
        )
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}

    shipments["_shipment_id_normalized"] = (
        shipments["shipment_id"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    matches = shipments[
        shipments["_shipment_id_normalized"] == normalized_id
    ].drop(columns=["_shipment_id_normalized"])

    if matches.empty:
        return {
            "success": False,
            "error": (
                f"Shipment {normalized_id} was not found. "
                f"Loaded {len(shipments)} shipments."
            ),
        }

    return clean_for_json({
        "success": True,
        "shipment": matches.iloc[0].to_dict(),
        "source_references": [
            f"[SRC:shipment/{normalized_id}]",
        ],
    })


def get_shipment_items(shipment_id: str) -> dict:
    """Return all raw line items belonging to a shipment."""

    normalized_id = normalize_text(shipment_id)

    try:
        items = read_csv(
            "shipment_items.csv",
            dtype={
                "shipment_item_id": str,
                "shipment_id": str,
                "sku": str,
                "declared_hs_code": str,
                "batch_id": str,
            },
        )
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}

    items["_shipment_id_normalized"] = (
        items["shipment_id"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    matches = items[
        items["_shipment_id_normalized"] == normalized_id
    ].drop(columns=["_shipment_id_normalized"]).copy()

    if matches.empty:
        return {
            "success": False,
            "error": f"No line items found for {normalized_id}.",
        }

    return clean_for_json({
        "success": True,
        "shipment_id": normalized_id,
        "item_count": len(matches),
        "items": matches.to_dict(orient="records"),
        "source_references": [
            f"[SRC:shipment_items/{item_id}]"
            for item_id in matches["shipment_item_id"].astype(str).tolist()
        ],
    })


def get_shipment_parties(shipment_id: str) -> dict:
    """Return exporter and buyer records linked to a shipment."""

    shipment_result = get_shipment(shipment_id)

    if not shipment_result.get("success"):
        return shipment_result

    shipment = shipment_result["shipment"]

    try:
        exporters = read_csv(
            "exporters.csv",
            dtype={"exporter_id": str},
        )
        buyers = read_csv(
            "buyers.csv",
            dtype={"buyer_id": str, "market_code": str},
        )
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}

    exporter_id = normalize_text(shipment.get("exporter_id"))
    buyer_id = normalize_text(shipment.get("buyer_id"))

    exporter_match = exporters[
        exporters["exporter_id"]
        .astype(str)
        .str.strip()
        .str.upper()
        == exporter_id
    ]

    buyer_match = buyers[
        buyers["buyer_id"]
        .astype(str)
        .str.strip()
        .str.upper()
        == buyer_id
    ]

    return clean_for_json({
        "success": True,
        "shipment_id": normalize_text(shipment_id),
        "exporter": (
            exporter_match.iloc[0].to_dict()
            if not exporter_match.empty
            else None
        ),
        "buyer": (
            buyer_match.iloc[0].to_dict()
            if not buyer_match.empty
            else None
        ),
        "source_references": [
            f"[SRC:shipment_parties/{party_id}]"
            for party_id in (
                exporter_match.get("exporter_id", []).astype(str).tolist()
                + buyer_match.get("buyer_id", []).astype(str).tolist()
            )
        ],
    })
