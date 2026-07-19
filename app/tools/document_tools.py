from __future__ import annotations

from app.tools.data_access import normalize_text, read_csv
from app.utils.serialization import clean_for_json


def get_shipment_documents(shipment_id: str) -> dict:
    """
    Return raw document-register records for a shipment.

    This function deliberately does not classify documents as valid,
    missing, expired, or blocking. Those are reasoning tasks for the agent.
    """

    normalized_id = normalize_text(shipment_id)

    try:
        documents = read_csv(
            "document_register.csv",
            dtype={
                "document_id": str,
                "shipment_id": str,
                "sku": str,
                "version": str,
                "supersedes_document_id": str,
            },
        )
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}

    documents["_shipment_id_normalized"] = (
        documents["shipment_id"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    matches = documents[
        documents["_shipment_id_normalized"] == normalized_id
    ].drop(columns=["_shipment_id_normalized"]).copy()

    return clean_for_json({
        "success": True,
        "shipment_id": normalized_id,
        "document_count": len(matches),
        "documents": matches.to_dict(orient="records"),
    })


def get_document_fields(document_ids: list[str]) -> dict:
    """Return extracted raw fields for one or more document IDs."""

    normalized_ids = {
        normalize_text(document_id)
        for document_id in document_ids
        if normalize_text(document_id)
    }

    if not normalized_ids:
        return {
            "success": True,
            "field_count": 0,
            "fields": [],
        }

    try:
        fields = read_csv(
            "document_extracted_fields.csv",
            dtype={
                "document_id": str,
                "field_name": str,
                "field_value_raw": str,
            },
        )
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc)}

    fields["_document_id_normalized"] = (
        fields["document_id"]
        .astype(str)
        .str.strip()
        .str.upper()
    )

    matches = fields[
        fields["_document_id_normalized"].isin(normalized_ids)
    ].drop(columns=["_document_id_normalized"]).copy()

    return clean_for_json({
        "success": True,
        "field_count": len(matches),
        "fields": matches.to_dict(orient="records"),
    })


def get_shipment_document_evidence(shipment_id: str) -> dict:
    """Return document metadata together with extracted raw fields."""

    documents_result = get_shipment_documents(shipment_id)

    if not documents_result.get("success"):
        return documents_result

    documents = documents_result["documents"]
    document_ids = [
        document["document_id"]
        for document in documents
        if document.get("document_id")
    ]

    fields_result = get_document_fields(document_ids)

    if not fields_result.get("success"):
        return {
            "success": False,
            "error": (
                "Document metadata was loaded, but extracted fields "
                f"could not be loaded: {fields_result.get('error')}"
            ),
            "documents": documents,
        }

    fields_by_document: dict[str, list[dict]] = {}

    for field in fields_result.get("fields", []):
        fields_by_document.setdefault(
            field["document_id"],
            [],
        ).append(field)

    enriched_documents = []

    for document in documents:
        enriched_documents.append({
            **document,
            "extracted_fields": fields_by_document.get(
                document.get("document_id"),
                [],
            ),
        })

    return clean_for_json({
        "success": True,
        "shipment_id": normalize_text(shipment_id),
        "document_count": len(enriched_documents),
        "documents": enriched_documents,
        "source_references": [
            f"[SRC:shipment_documents/{document_id}]"
            for document_id in document_ids
        ],
    })
