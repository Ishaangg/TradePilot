from datetime import date, datetime


REQUIRED_SHIPMENT_FIELDS = [
    "shipment_id",
    "exporter_id",
    "buyer_id",
    "origin_city",
    "destination_country",
    "destination_port",
    "preferred_transport",
    "gross_weight_kg",
    "invoice_value_usd",
    "delivery_deadline",
]


def assess_shipment_data(
    shipment: dict,
    items: list[dict],
    missing_documents: list[str],
) -> dict:
    """Validate and calculate a shipment assessment."""

    missing_fields = [
        field
        for field in REQUIRED_SHIPMENT_FIELDS
        if shipment.get(field) in (None, "", "nan")
    ]

    warnings: list[str] = []

    calculated_value = round(
        sum(float(item.get("line_value_usd", 0)) for item in items),
        2,
    )

    calculated_weight = round(
        sum(float(item.get("gross_weight_kg", 0)) for item in items),
        2,
    )

    declared_value = float(shipment.get("invoice_value_usd", 0))
    declared_weight = float(shipment.get("gross_weight_kg", 0))

    value_tolerance = max(1.0, declared_value * 0.01)
    weight_tolerance = max(1.0, declared_weight * 0.02)

    if abs(calculated_value - declared_value) > value_tolerance:
        warnings.append(
            "Shipment invoice value does not match the item total."
        )

    if abs(calculated_weight - declared_weight) > weight_tolerance:
        warnings.append(
            "Shipment weight does not match the item weight total."
        )

    if missing_documents:
        warnings.append(
            f"{len(missing_documents)} required document(s) are missing."
        )

    risk_score = float(shipment.get("risk_score", 0))

    if risk_score >= 70:
        warnings.append("Shipment has a high risk score.")

    special_handling = str(
        shipment.get("special_handling", "")
    ).lower()

    if special_handling and special_handling != "standard":
        warnings.append(
            "Shipment requires non-standard handling."
        )

    deadline = shipment.get("delivery_deadline")

    if isinstance(deadline, str):
        deadline_date = datetime.fromisoformat(
            deadline.replace("Z", "+00:00")
        ).date()
    else:
        deadline_date = deadline

    if deadline_date and deadline_date < date.today():
        warnings.append("The shipment deadline has already passed.")

    if missing_fields:
        decision = "BLOCKED"
    elif missing_documents or warnings:
        decision = "REVIEW_REQUIRED"
    else:
        decision = "READY"

    next_actions = []

    if missing_fields:
        next_actions.append("Complete missing shipment fields.")

    if missing_documents:
        next_actions.append("Collect or generate missing documents.")

    if risk_score >= 70:
        next_actions.append("Request human compliance approval.")

    if decision != "BLOCKED":
        next_actions.append("Request freight quotations.")

    return {
        "shipment_id": shipment.get("shipment_id"),
        "decision": decision,
        "validation": {
            "valid": not missing_fields,
            "missing_fields": missing_fields,
            "warnings": warnings,
        },
        "calculated_item_value_usd": calculated_value,
        "calculated_item_weight_kg": calculated_weight,
        "missing_documents": missing_documents,
        "next_actions": next_actions,
    }