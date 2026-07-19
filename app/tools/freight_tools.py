from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.tools.data_access import read_csv
from app.utils.serialization import clean_for_json
from datetime import timedelta


COUNTRY_ALIASES = {
    "NL": {"NL", "NETHERLANDS", "THE NETHERLANDS"},
    "DE": {"DE", "GERMANY", "FEDERAL REPUBLIC OF GERMANY"},
    "FR": {"FR", "FRANCE", "FRENCH REPUBLIC"},
    "IT": {"IT", "ITALY", "ITALIA"},
    "ES": {"ES", "SPAIN", "ESPAÑA"},
}


def _normalize_country(value: str) -> str:
    normalized = str(value).strip().upper()

    for market_code, aliases in COUNTRY_ALIASES.items():
        if normalized in aliases:
            return market_code

    return normalized


def get_matching_freight_rates(
    origin_city: str,
    destination_country: str,
    destination_port: str,
    transport_mode: str,
    gross_weight_kg: float,
    shipment_date: str,
) -> dict:
    """
    Return raw rate cards compatible with shipment facts.

    This tool filters by lane, mode, weight range, and validity only.
    It does not recommend a provider.
    """

    try:
        rates = read_csv(
            "freight_rates.csv",
            dtype={
                "rate_id": str,
                "destination_country_raw": str,
            },
        )
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}

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

    rates["valid_from_parsed"] = pd.to_datetime(
        rates["valid_from"],
        errors="coerce",
    ).dt.date

    rates["valid_to_parsed"] = pd.to_datetime(
        rates["valid_to"],
        errors="coerce",
    ).dt.date

    rates["weight_min_kg_parsed"] = pd.to_numeric(
        rates["weight_min_kg"],
        errors="coerce",
    )

    rates["weight_max_kg_parsed"] = pd.to_numeric(
        rates["weight_max_kg"],
        errors="coerce",
    )

    requested_country = _normalize_country(
        destination_country
    )

    rate_country_codes = rates[
        "destination_country_raw"
    ].astype(str).map(_normalize_country)

    matches = rates[
        rates["origin_city"]
            .astype(str)
            .str.strip()
            .str.casefold()
            .eq(origin_city.strip().casefold())
        &
        rate_country_codes.eq(requested_country)
        &
        rates["destination_port"]
            .astype(str)
            .str.strip()
            .str.casefold()
            .eq(destination_port.strip().casefold())
        &
        rates["transport_mode"]
            .astype(str)
            .str.strip()
            .str.casefold()
            .eq(transport_mode.strip().casefold())
        &
        rates["weight_min_kg_parsed"].le(gross_weight_kg)
        &
        rates["weight_max_kg_parsed"].ge(gross_weight_kg)
        &
        rates["valid_from_parsed"].le(requested_date)
        &
        rates["valid_to_parsed"].ge(requested_date)
    ].copy()

    matches = matches.drop(
        columns=[
            "valid_from_parsed",
            "valid_to_parsed",
            "weight_min_kg_parsed",
            "weight_max_kg_parsed",
        ],
    )

    return clean_for_json({
        "success": True,
        "match_count": len(matches),
        "rates": matches.to_dict(orient="records"),
        "source_references": [
            f"[SRC:freight_rates/{rate_id}]"
            for rate_id in matches["rate_id"].astype(str).tolist()
        ],
        "matching_facts": {
            "origin_city": origin_city,
            "destination_country_input": destination_country,
            "destination_market_normalized": requested_country,
            "destination_port": destination_port,
            "transport_mode": transport_mode,
            "gross_weight_kg": gross_weight_kg,
            "shipment_date": shipment_date,
        },
    })


def calculate_freight_quotes(
    rates: list[dict],
    gross_weight_kg: float,
    volume_cbm: float,
) -> dict:
    """
    Calculate estimated quote totals from raw rate cards.

    Currency conversion is intentionally not performed. Quotes in different
    currencies must not be directly ranked by cost without an FX source.
    """

    quotes = []

    for rate in rates:
        try:
            rate_basis = str(
                rate.get("rate_basis", "")
            ).strip().lower()

            base_rate = float(rate.get("base_rate") or 0)
            minimum_charge = float(
                rate.get("minimum_charge") or 0
            )
            origin_charges = float(
                rate.get("origin_charges") or 0
            )
            destination_charges = float(
                rate.get("destination_charges") or 0
            )

            if rate_basis == "per_kg":
                raw_freight_charge = (
                    base_rate * gross_weight_kg
                )

            elif rate_basis == "per_cbm":
                raw_freight_charge = (
                    base_rate * volume_cbm
                )

            elif rate_basis == "per_container":
                raw_freight_charge = base_rate

            else:
                quotes.append({
                    "rate_id": rate.get("rate_id"),
                    "calculation_error": (
                        f"Unsupported rate basis: {rate_basis}"
                    ),
                })
                continue

            freight_charge = max(
                raw_freight_charge,
                minimum_charge,
            )

            total = (
                freight_charge
                + origin_charges
                + destination_charges
            )

            quotes.append({
                "quote_id": f"QUOTE-{rate.get('rate_id')}",
                "rate_id": rate.get("rate_id"),
                "provider_name": rate.get("provider_name"),
                "transport_mode": rate.get("transport_mode"),
                "rate_basis": rate_basis,
                "base_rate": round(base_rate, 2),
                "calculation_quantity": (
                    gross_weight_kg
                    if rate_basis == "per_kg"
                    else (
                        volume_cbm
                        if rate_basis == "per_cbm"
                        else 1
                    )
                ),
                "raw_freight_charge": round(
                    raw_freight_charge,
                    2,
                ),
                "minimum_charge": round(
                    minimum_charge,
                    2,
                ),
                "minimum_charge_applied": (
                    minimum_charge > raw_freight_charge
                ),
                "freight_charge": round(
                    freight_charge,
                    2,
                ),
                "origin_charges": round(
                    origin_charges,
                    2,
                ),
                "destination_charges": round(
                    destination_charges,
                    2,
                ),
                "estimated_total": round(total, 2),
                "currency": rate.get("currency"),
                "estimated_transit_days": int(
                    rate.get("estimated_transit_days")
                ),
                "valid_from": rate.get("valid_from"),
                "valid_to": rate.get("valid_to"),
                "source_references": [
                    f"[SRC:freight_rates/{rate.get('rate_id')}]",
                    f"[SRC:freight_calculations/QUOTE-{rate.get('rate_id')}]",
                ],
            })

        except (TypeError, ValueError) as exc:
            quotes.append({
                "rate_id": rate.get("rate_id"),
                "calculation_error": str(exc),
            })

    return clean_for_json({
        "success": True,
        "quote_count": len(quotes),
        "quotes": quotes,
    })


def analyze_freight_options(
    quotes: list[dict],
    shipment_date: str,
    delivery_deadline: str,
) -> dict:
    """
    Add factual deadline and currency-comparability information.

    The LLM freight specialist should infer trade-offs and recommendations.
    """

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

    analyzed = []

    currencies = {
        str(quote.get("currency")).strip().upper()
        for quote in quotes
        if quote.get("currency")
        and not quote.get("calculation_error")
    }

    for quote in quotes:
        if quote.get("calculation_error"):
            analyzed.append(quote)
            continue

        transit_days = int(
            quote.get("estimated_transit_days") or 0
        )

        analyzed.append({
            **quote,
            "available_days": available_days,
            "estimated_arrival_date": (
    start_date + timedelta(days=transit_days)
    ).isoformat(),
            "deadline_feasible_on_transit_estimate": (
                transit_days <= available_days
            ),
            "cost_comparable_without_fx": (
                len(currencies) <= 1
            ),
            "source_references": sorted(set(
                quote.get("source_references", [])
                + [
                    f"[SRC:freight_calculations/{quote.get('quote_id')}]",
                ]
            )),
        })

    return clean_for_json({
        "success": True,
        "available_days": available_days,
        "currencies_present": sorted(currencies),
        "cross_currency_cost_ranking_safe": (
            len(currencies) <= 1
        ),
        "options": analyzed,
        "analysis_note": (
            "Factual option analysis only. No recommended provider "
            "has been selected."
        ),
    })
