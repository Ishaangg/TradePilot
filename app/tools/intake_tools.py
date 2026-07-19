from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.utils.serialization import clean_for_json


def compare_shipment_totals(
    shipment: dict,
    items: list[dict],
) -> dict:
    """
    Calculate raw shipment-to-line-item discrepancies.

    This function reports arithmetic facts only. It does not assign
    READY, BLOCKED, REVIEW_REQUIRED, risk scores, or next actions.
    """

    item_value = round(
        sum(
            float(item.get("line_value") or 0)
            for item in items
        ),
        2,
    )

    item_weight = round(
        sum(
            float(item.get("gross_weight_kg") or 0)
            for item in items
        ),
        2,
    )

    item_volume = round(
        sum(
            float(item.get("volume_cbm") or 0)
            for item in items
        ),
        3,
    )

    declared_value = float(
        shipment.get("declared_total_value") or 0
    )
    declared_weight = float(
        shipment.get("declared_gross_weight_kg") or 0
    )
    declared_volume = float(
        shipment.get("declared_volume_cbm") or 0
    )

    return clean_for_json({
        "shipment_id": shipment.get("shipment_id"),
        "calculated_from_items": {
            "value": item_value,
            "gross_weight_kg": item_weight,
            "volume_cbm": item_volume,
        },
        "declared_on_shipment": {
            "value": declared_value,
            "gross_weight_kg": declared_weight,
            "volume_cbm": declared_volume,
        },
        "differences": {
            "value": round(declared_value - item_value, 2),
            "gross_weight_kg": round(
                declared_weight - item_weight,
                2,
            ),
            "volume_cbm": round(
                declared_volume - item_volume,
                3,
            ),
        },
        "source_references": [
            f"[SRC:shipment/{shipment.get('shipment_id')}]",
            *[
                f"[SRC:shipment_items/{item.get('shipment_item_id')}]"
                for item in items
            ],
        ],
    })


def get_timeline_facts(shipment: dict) -> dict:
    """Return factual date intervals for shipment-stage reasoning."""

    shipment_date_raw = shipment.get("shipment_date")
    deadline_raw = shipment.get("delivery_deadline")

    shipment_date = _parse_date(shipment_date_raw)
    deadline = _parse_date(deadline_raw)

    return clean_for_json({
        "shipment_id": shipment.get("shipment_id"),
        "shipment_date": shipment_date,
        "delivery_deadline": deadline,
        "days_from_shipment_date_to_deadline": (
            (deadline - shipment_date).days
            if shipment_date and deadline
            else None
        ),
        "days_from_today_to_deadline": (
            (deadline - date.today()).days
            if deadline
            else None
        ),
        "current_stage": shipment.get("current_stage"),
    })


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    try:
        return datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        ).date()
    except ValueError:
        return None
