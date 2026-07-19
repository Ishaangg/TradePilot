from __future__ import annotations

from typing import Any

from app.schemas import EvidenceProvenance, EvidenceSourceResult, EvidenceSourceStatus
from app.tools.data_access import normalize_text, read_csv
from app.tools.document_tools import get_shipment_document_evidence
from app.tools.shipment_tools import (
    get_shipment,
    get_shipment_items,
    get_shipment_parties,
)
from app.utils.serialization import clean_for_json


def _source_result(
    source_name: str,
    result: dict[str, Any],
    *,
    dataset: str,
    query: dict[str, Any],
) -> dict[str, Any]:
    """Turn one tool result into an explicit, traceable source outcome."""

    success = bool(result.get("success"))
    records: list[dict[str, Any]] = []
    for key in (
        "shipment", "items", "documents", "requirements", "rules",
        "artworks", "declarations", "reports", "operator_records",
    ):
        value = result.get(key)
        if isinstance(value, dict):
            records.append(value)
        elif isinstance(value, list):
            records.extend(item for item in value if isinstance(item, dict))

    record_ids: list[str] = []
    for record in records:
        for key in (
            "shipment_id", "shipment_item_id", "document_id", "requirement_id",
            "rule_id", "artwork_id", "declaration_id", "lab_report_id",
            "operator_record_id", "sku",
        ):
            value = record.get(key)
            if value not in (None, ""):
                record_ids.append(str(value))
                break

    provenance = EvidenceProvenance(
        source_name=source_name,
        source_kind="csv",
        dataset=dataset,
        query=query,
        record_ids=sorted(set(record_ids)),
    )
    outcome = EvidenceSourceResult(
        source_name=source_name,
        status=(EvidenceSourceStatus.SUCCESS if success else EvidenceSourceStatus.ERROR),
        provenance=provenance,
        record_count=len(records),
        error=None if success else str(result.get("error", "Unknown source error")),
    )
    return outcome.model_dump(mode="json")


def _collection_failure(
    source_name: str,
    result: dict[str, Any],
    *,
    dataset: str,
    query: dict[str, Any],
    source_results: list[dict[str, Any]],
) -> dict[str, Any]:
    source_results.append(
        _source_result(source_name, result, dataset=dataset, query=query)
    )
    return {
        "success": False,
        "error": result.get("error", f"{source_name} failed."),
        "source_results": source_results,
        "collection_errors": [
            source for source in source_results if source["status"] == "ERROR"
        ],
    }


def get_product_context(sku: str) -> dict:
    """Return raw product and component records for one SKU."""

    normalized_sku = normalize_text(sku)

    try:
        products = read_csv(
            "products.csv",
            dtype={
                "sku": str,
                "style_code": str,
                "hs6_reference": str,
                "manufacturer_id": str,
            },
        )
        components = read_csv(
            "product_components.csv",
            dtype={
                "component_id": str,
                "sku": str,
                "supplier_id": str,
                "supplier_material_code": str,
            },
        )
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}

    product_match = products[
        products["sku"]
        .astype(str)
        .str.strip()
        .str.upper()
        == normalized_sku
    ]

    if product_match.empty:
        return {
            "success": False,
            "error": f"Product {normalized_sku} was not found.",
        }

    component_matches = components[
        components["sku"]
        .astype(str)
        .str.strip()
        .str.upper()
        == normalized_sku
    ].copy()

    return clean_for_json({
        "success": True,
        "sku": normalized_sku,
        "product": product_match.iloc[0].to_dict(),
        "component_count": len(component_matches),
        "components": component_matches.to_dict(orient="records"),
    })


def get_label_artworks(
    sku: str,
    market_code: str | None = None,
) -> dict:
    """Return raw label-artwork records for a product."""

    normalized_sku = normalize_text(sku)
    normalized_market = normalize_text(market_code)

    try:
        labels = read_csv(
            "label_artworks.csv",
            dtype={
                "artwork_id": str,
                "sku": str,
                "market_code": str,
                "version": str,
            },
        )
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}

    matches = labels[
        labels["sku"]
        .astype(str)
        .str.strip()
        .str.upper()
        == normalized_sku
    ].copy()

    if normalized_market:
        matches = matches[
            matches["market_code"]
            .astype(str)
            .str.strip()
            .str.upper()
            == normalized_market
        ]

    return clean_for_json({
        "success": True,
        "sku": normalized_sku,
        "market_code": normalized_market or None,
        "artwork_count": len(matches),
        "artworks": matches.to_dict(orient="records"),
    })


def get_supplier_declarations(sku: str) -> dict:
    """Return supplier declarations that explicitly or materially relate to a SKU."""

    product_result = get_product_context(sku)

    if not product_result.get("success"):
        return product_result

    product = product_result["product"]
    components = product_result["components"]

    supplier_ids = {
        normalize_text(component.get("supplier_id"))
        for component in components
        if normalize_text(component.get("supplier_id"))
    }

    material_codes = {
        normalize_text(component.get("supplier_material_code"))
        for component in components
        if normalize_text(component.get("supplier_material_code"))
    }

    normalized_sku = normalize_text(sku)

    try:
        declarations = read_csv(
            "supplier_declarations.csv",
            dtype={
                "declaration_id": str,
                "supplier_id": str,
                "material_code": str,
                "sku_reference": str,
            },
        )
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}

    supplier_series = (
        declarations["supplier_id"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    material_series = (
        declarations["material_code"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    sku_series = (
        declarations["sku_reference"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    matches = declarations[
        sku_series.eq(normalized_sku)
        | material_series.isin(material_codes)
        | supplier_series.isin(supplier_ids)
    ].copy()

    return clean_for_json({
        "success": True,
        "sku": normalized_sku,
        "declaration_count": len(matches),
        "declarations": matches.to_dict(orient="records"),
        "matching_basis": {
            "sku": normalized_sku,
            "supplier_ids": sorted(supplier_ids),
            "material_codes": sorted(material_codes),
        },
    })


def get_product_lab_evidence(sku: str) -> dict:
    """
    Return laboratory reports and samples potentially related to a SKU.

    Matching is deliberately broad:
    - explicit SKU reference
    - product component material code
    - product component supplier
    """

    product_result = get_product_context(sku)

    if not product_result.get("success"):
        return product_result

    normalized_sku = normalize_text(sku)
    components = product_result["components"]

    supplier_ids = {
        normalize_text(component.get("supplier_id"))
        for component in components
        if normalize_text(component.get("supplier_id"))
    }

    material_codes = {
        normalize_text(component.get("supplier_material_code"))
        for component in components
        if normalize_text(component.get("supplier_material_code"))
    }

    try:
        reports = read_csv(
            "lab_reports.csv",
            dtype={
                "lab_report_id": str,
                "supplier_id": str,
            },
        )
        samples = read_csv(
            "lab_report_samples.csv",
            dtype={
                "sample_id": str,
                "lab_report_id": str,
                "material_code": str,
                "sku_reference": str,
                "batch_or_lot": str,
            },
        )
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}

    sample_sku = (
        samples["sku_reference"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    sample_material = (
        samples["material_code"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    report_supplier = (
        reports["supplier_id"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    report_ids_from_supplier = set(
        reports.loc[
            report_supplier.isin(supplier_ids),
            "lab_report_id",
        ]
        .astype(str)
        .tolist()
    )

    matching_samples = samples[
        sample_sku.eq(normalized_sku)
        | sample_material.isin(material_codes)
        | samples["lab_report_id"]
            .astype(str)
            .isin(report_ids_from_supplier)
    ].copy()

    matching_report_ids = set(
        matching_samples["lab_report_id"]
        .astype(str)
        .tolist()
    )

    matching_reports = reports[
        reports["lab_report_id"]
        .astype(str)
        .isin(matching_report_ids)
    ].copy()

    samples_by_report: dict[str, list[dict]] = {}

    for sample in matching_samples.to_dict(orient="records"):
        samples_by_report.setdefault(
            str(sample["lab_report_id"]),
            [],
        ).append(sample)

    enriched_reports = []

    for report in matching_reports.to_dict(orient="records"):
        enriched_reports.append({
            **report,
            "samples": samples_by_report.get(
                str(report["lab_report_id"]),
                [],
            ),
        })

    return clean_for_json({
        "success": True,
        "sku": normalized_sku,
        "report_count": len(enriched_reports),
        "reports": enriched_reports,
        "matching_basis": {
            "explicit_sku": normalized_sku,
            "supplier_ids": sorted(supplier_ids),
            "material_codes": sorted(material_codes),
        },
    })


def get_responsible_operator(buyer_id: str) -> dict:
    """Return raw EU economic-operator records associated with a buyer."""

    normalized_buyer_id = normalize_text(buyer_id)

    try:
        operators = read_csv(
            "responsible_operators.csv",
            dtype={
                "operator_record_id": str,
                "buyer_id": str,
            },
        )
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}

    matches = operators[
        operators["buyer_id"]
        .astype(str)
        .str.strip()
        .str.upper()
        == normalized_buyer_id
    ].copy()

    return clean_for_json({
        "success": True,
        "buyer_id": normalized_buyer_id,
        "operator_record_count": len(matches),
        "operator_records": matches.to_dict(orient="records"),
    })


def get_regulatory_rules(
    domains: list[str] | None = None,
) -> dict:
    """
    Return regulatory reference rows.

    The tool retrieves requirements only. It does not decide applicability
    or determine whether evidence is sufficient.
    """

    try:
        rules = read_csv(
            "regulatory_rules.csv",
            dtype={"rule_id": str, "domain": str},
        )
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}

    if domains:
        normalized_domains = {
            normalize_text(domain)
            for domain in domains
            if normalize_text(domain)
        }

        domain_series = (
            rules["domain"]
            .astype(str)
            .str.strip()
            .str.upper()
        )

        rules = rules[
            domain_series.isin(normalized_domains)
        ].copy()

    return clean_for_json({
        "success": True,
        "rule_count": len(rules),
        "rules": rules.to_dict(orient="records"),
    })


def get_document_requirements() -> dict:
    """Return stage and evidence-reference descriptions."""

    try:
        requirements = read_csv(
            "document_requirements.csv",
            dtype={
                "requirement_id": str,
                "document_family": str,
                "source_rule_ids": str,
            },
        )
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}

    return clean_for_json({
        "success": True,
        "requirement_count": len(requirements),
        "requirements": requirements.to_dict(orient="records"),
    })


def collect_compliance_evidence(shipment_id: str) -> dict:
    """
    Gather normalized raw facts for compliance reasoning.

    This function does not return a compliance decision, risk score,
    blocker label, warning label, or evidence status.
    """

    normalized_id = normalize_text(shipment_id)
    source_results: list[dict[str, Any]] = []

    shipment_result = get_shipment(shipment_id)
    if not shipment_result.get("success"):
        return _collection_failure(
            "shipment", shipment_result, dataset="shipments.csv",
            query={"shipment_id": normalized_id},
            source_results=source_results,
        )
    source_results.append(_source_result(
        "shipment", shipment_result,
        dataset="shipments.csv",
        query={"shipment_id": normalized_id},
    ))

    items_result = get_shipment_items(shipment_id)
    if not items_result.get("success"):
        return _collection_failure(
            "shipment_items", items_result, dataset="shipment_items.csv",
            query={"shipment_id": normalized_id},
            source_results=source_results,
        )
    source_results.append(_source_result(
        "shipment_items", items_result,
        dataset="shipment_items.csv",
        query={"shipment_id": normalized_id},
    ))

    parties_result = get_shipment_parties(shipment_id)
    documents_result = get_shipment_document_evidence(shipment_id)
    requirements_result = get_document_requirements()
    rules_result = get_regulatory_rules()

    source_results.extend([
        _source_result(
            "shipment_parties", parties_result,
            dataset="exporters.csv + buyers.csv",
            query={"shipment_id": normalized_id},
        ),
        _source_result(
            "shipment_documents", documents_result,
            dataset="document_register.csv + document_extracted_fields.csv",
            query={"shipment_id": normalized_id},
        ),
        _source_result(
            "document_requirements", requirements_result,
            dataset="document_requirements.csv", query={},
        ),
        _source_result(
            "regulatory_rules", rules_result,
            dataset="regulatory_rules.csv", query={},
        ),
    ])

    shipment = shipment_result["shipment"]
    product_contexts = []
    label_artworks = []
    declarations = []
    laboratory_evidence = []

    for item in items_result["items"]:
        sku = item.get("sku")

        if not sku:
            product_contexts.append({
                "success": False,
                "error": "Shipment item has no SKU.",
                "shipment_item_id": item.get("shipment_item_id"),
            })
            source_results.append(_source_result(
                "product_context",
                product_contexts[-1],
                dataset="products.csv + product_components.csv",
                query={"sku": None, "shipment_item_id": item.get("shipment_item_id")},
            ))
            continue

        product_result = get_product_context(sku)
        label_result = get_label_artworks(sku, shipment.get("destination_market"))
        declaration_result = get_supplier_declarations(sku)
        lab_result = get_product_lab_evidence(sku)
        product_contexts.append(product_result)
        label_artworks.append(label_result)
        declarations.append(declaration_result)
        laboratory_evidence.append(lab_result)
        source_results.extend([
            _source_result(
                "product_context", product_result,
                dataset="products.csv + product_components.csv",
                query={"sku": normalize_text(sku)},
            ),
            _source_result(
                "label_artworks", label_result,
                dataset="label_artworks.csv",
                query={"sku": normalize_text(sku), "market_code": shipment.get("destination_market")},
            ),
            _source_result(
                "supplier_declarations", declaration_result,
                dataset="supplier_declarations.csv",
                query={"sku": normalize_text(sku)},
            ),
            _source_result(
                "laboratory_evidence", lab_result,
                dataset="lab_reports.csv + lab_report_samples.csv",
                query={"sku": normalize_text(sku)},
            ),
        ])

    operator_result = get_responsible_operator(shipment.get("buyer_id", ""))
    source_results.append(_source_result(
        "responsible_operators", operator_result,
        dataset="responsible_operators.csv",
        query={"buyer_id": normalize_text(shipment.get("buyer_id", ""))},
    ))

    collection_errors = [
        source for source in source_results if source["status"] == "ERROR"
    ]

    return clean_for_json({
        "success": True,
        "shipment_id": normalized_id,
        "shipment": shipment,
        "items": items_result["items"],
        "parties": {
            "exporter": parties_result.get("exporter"),
            "buyer": parties_result.get("buyer"),
        },
        "products": product_contexts,
        "documents": documents_result.get("documents", []),
        "destination_label_artworks": label_artworks,
        "supplier_declarations": declarations,
        "laboratory_evidence": laboratory_evidence,
        "responsible_operator_records": operator_result.get(
            "operator_records",
            [],
        ),
        "document_requirements": requirements_result.get(
            "requirements",
            [],
        ),
        "regulatory_rules": rules_result.get("rules", []),
        "source_results": source_results,
        "collection_errors": collection_errors,
        "collection_note": (
            "Raw evidence collection only. Every source includes its "
            "status and provenance; no compliance decision or evidence "
            "sufficiency classification has been precomputed."
        ),
    })
