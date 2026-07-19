from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def clean_for_json(value: Any) -> Any:
    """Convert Pandas and NumPy values into valid JSON values."""

    if isinstance(value, dict):
        return {
            str(key): clean_for_json(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [clean_for_json(item) for item in value]
    
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()

    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if hasattr(value, "item"):
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass

    return value


def get_matching_freight_rates(
    origin_city: str,
    destination_country: str,
    destination_port: str,
    transport_mode: str,
    gross_weight_kg: float,
    shipment_date: str,
) -> dict:
    """
    Find freight rate cards compatible with a shipment.

    Matching is based on:
    - origin city
    - destination country
    - destination port
    - transport mode
    - supported weight range
    - rate validity
    """

    rates_path = DATA_DIR / "freight_rates.csv"

    if not rates_path.exists():
        return {
            "success": False,
            "error": f"Freight rates dataset not found: {rates_path}",
        }

    rates = pd.read_csv(
        rates_path,
        encoding="utf-8-sig",
    )

    required_columns = [
        "rate_id",
        "provider_name",
        "origin_city",
        "destination_country",
        "destination_port",
        "transport_mode",
        "min_weight_kg",
        "max_weight_kg",
        "base_rate",
        "rate_basis",
        "estimated_transit_days",
        "origin_charges_usd",
        "destination_charges_usd",
        "currency",
        "valid_from",
        "valid_to",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in rates.columns
    ]

    if missing_columns:
        return {
            "success": False,
            "error": (
                "Freight rate dataset is missing columns: "
                + ", ".join(missing_columns)
            ),
        }

    try:
        requested_date = datetime.fromisoformat(
            shipment_date.replace("Z", "+00:00")
        ).date()
    except ValueError:
        return {
            "success": False,
            "error": (
                f"Invalid shipment_date: {shipment_date}. "
                "Use YYYY-MM-DD format."
            ),
        }

    rates["valid_from"] = pd.to_datetime(
        rates["valid_from"],
        errors="coerce",
    ).dt.date

    rates["valid_to"] = pd.to_datetime(
        rates["valid_to"],
        errors="coerce",
    ).dt.date

    normalized_origin = origin_city.strip().lower()
    normalized_country = destination_country.strip().lower()
    normalized_port = destination_port.strip().lower()
    normalized_mode = transport_mode.strip().lower()

    matches = rates[
        (rates["origin_city"].astype(str).str.strip().str.lower()
         == normalized_origin)
        &
        (
            rates["destination_country"]
            .astype(str)
            .str.strip()
            .str.lower()
            == normalized_country
        )
        &
        (
            rates["destination_port"]
            .astype(str)
            .str.strip()
            .str.lower()
            == normalized_port
        )
        &
        (
            rates["transport_mode"]
            .astype(str)
            .str.strip()
            .str.lower()
            == normalized_mode
        )
        &
        (
            pd.to_numeric(
                rates["min_weight_kg"],
                errors="coerce",
            ) <= gross_weight_kg
        )
        &
        (
            pd.to_numeric(
                rates["max_weight_kg"],
                errors="coerce",
            ) >= gross_weight_kg
        )
        &
        (rates["valid_from"] <= requested_date)
        &
        (rates["valid_to"] >= requested_date)
    ].copy()

    if matches.empty:
        return {
            "success": True,
            "match_count": 0,
            "rates": [],
            "message": "No compatible freight rate cards were found.",
        }

    return clean_for_json({
        "success": True,
        "match_count": len(matches),
        "rates": matches.to_dict(orient="records"),
    })


def calculate_freight_quotes(
    rates: list[dict],
    gross_weight_kg: float,
    volume_cbm: float,
) -> dict:
    """
    Convert freight rate cards into estimated quotations.

    Supported rate bases:
    - per_kg
    - per_cbm
    - per_container
    """

    if not rates:
        return {
            "success": True,
            "quote_count": 0,
            "quotes": [],
        }

    quotes: list[dict] = []

    for rate in rates:
        rate_basis = str(rate.get("rate_basis", "")).strip().lower()
        base_rate = float(rate.get("base_rate", 0))
        origin_charges = float(rate.get("origin_charges_usd", 0))
        destination_charges = float(
            rate.get("destination_charges_usd", 0)
        )

        if rate_basis == "per_kg":
            freight_charge = base_rate * gross_weight_kg

        elif rate_basis == "per_cbm":
            chargeable_cbm = max(volume_cbm, 1.0)
            freight_charge = base_rate * chargeable_cbm

        elif rate_basis == "per_container":
            freight_charge = base_rate

        else:
            continue

        estimated_total = (
            freight_charge
            + origin_charges
            + destination_charges
        )

        quotes.append({
            "quote_id": f"QUOTE-{rate['rate_id']}",
            "rate_id": rate["rate_id"],
            "provider_name": rate["provider_name"],
            "transport_mode": rate["transport_mode"],
            "rate_basis": rate_basis,
            "base_rate": round(base_rate, 2),
            "freight_charge_usd": round(freight_charge, 2),
            "origin_charges_usd": round(origin_charges, 2),
            "destination_charges_usd": round(
                destination_charges,
                2,
            ),
            "estimated_total_usd": round(
                estimated_total,
                2,
            ),
            "estimated_transit_days": int(
                rate["estimated_transit_days"]
            ),
            "currency": rate.get("currency", "USD"),
            "quote_source": "SYNTHETIC_RATE_CARD",
        })

    return clean_for_json({
        "success": True,
        "quote_count": len(quotes),
        "quotes": quotes,
    })


def rank_freight_quotes(
    quotes: list[dict],
    shipment_date: str,
    delivery_deadline: str,
) -> dict:
    """
    Rank freight quotations by cost, speed, and deadline feasibility.
    """

    if not quotes:
        return {
            "success": True,
            "ranked_quotes": [],
            "recommendation": None,
            "message": "No quotations were available to rank.",
        }

    try:
        start_date = datetime.fromisoformat(
            shipment_date.replace("Z", "+00:00")
        ).date()

        deadline = datetime.fromisoformat(
            delivery_deadline.replace("Z", "+00:00")
        ).date()
    except ValueError as exc:
        return {
            "success": False,
            "error": f"Invalid date supplied: {exc}",
        }

    available_days = (deadline - start_date).days

    ranked_quotes = []

    min_cost = min(
        float(quote["estimated_total_usd"])
        for quote in quotes
    )

    min_transit = min(
        int(quote["estimated_transit_days"])
        for quote in quotes
    )

    for quote in quotes:
        cost = float(quote["estimated_total_usd"])
        transit_days = int(
            quote["estimated_transit_days"]
        )

        deadline_feasible = transit_days <= available_days

        cost_score = min_cost / cost if cost > 0 else 0
        speed_score = (
            min_transit / transit_days
            if transit_days > 0
            else 0
        )

        deadline_score = 1.0 if deadline_feasible else 0.0

        recommendation_score = round(
            (cost_score * 0.50)
            + (speed_score * 0.30)
            + (deadline_score * 0.20),
            4,
        )

        ranked_quote = {
            **quote,
            "available_days": available_days,
            "deadline_feasible": deadline_feasible,
            "recommendation_score": recommendation_score,
        }

        ranked_quotes.append(ranked_quote)

    ranked_quotes.sort(
        key=lambda quote: quote["recommendation_score"],
        reverse=True,
    )

    cheapest = min(
        ranked_quotes,
        key=lambda quote: quote["estimated_total_usd"],
    )

    fastest = min(
        ranked_quotes,
        key=lambda quote: quote["estimated_transit_days"],
    )

    feasible_quotes = [
        quote
        for quote in ranked_quotes
        if quote["deadline_feasible"]
    ]

    recommended = (
        feasible_quotes[0]
        if feasible_quotes
        else ranked_quotes[0]
    )

    for quote in ranked_quotes:
        labels = []

        if quote["quote_id"] == cheapest["quote_id"]:
            labels.append("CHEAPEST")

        if quote["quote_id"] == fastest["quote_id"]:
            labels.append("FASTEST")

        if quote["quote_id"] == recommended["quote_id"]:
            labels.append("RECOMMENDED")

        quote["ranking_labels"] = labels

    return clean_for_json({
        "success": True,
        "ranked_quotes": ranked_quotes,
        "recommendation": {
            "cheapest_quote_id": cheapest["quote_id"],
            "fastest_quote_id": fastest["quote_id"],
            "recommended_quote_id": recommended["quote_id"],
            "any_deadline_feasible": bool(feasible_quotes),
        },
    }) 