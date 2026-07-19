import warnings

import pytest
from starlette.testclient import TestClient

from app.schemas import (
    ApplicabilityStatus,
    CoordinatorDecision,
    EvidenceSourceStatus,
    SpecialistOutcome,
)
from app.tools import evidence_tools
from app.tools import document_tools


def test_canonical_decision_enums_match_prompt_contracts():
    assert {item.value for item in CoordinatorDecision} == {
        "READY_TO_PROCEED",
        "PROCEED_WITH_CONDITIONS",
        "HUMAN_REVIEW_REQUIRED",
        "BLOCKED_PENDING_EVIDENCE",
        "REJECTED",
    }
    assert {item.value for item in SpecialistOutcome} == {
        "SUPPORTS_COMPLIANCE",
        "INSUFFICIENT_EVIDENCE",
        "CONFLICTING_EVIDENCE",
        "NOT_APPLICABLE",
        "HUMAN_VERIFICATION_NEEDED",
    }
    assert {item.value for item in ApplicabilityStatus} == {
        "CONFIRMED", "PROVISIONAL", "UNCERTAIN",
    }


def test_compliance_evidence_has_source_status_and_provenance():
    result = evidence_tools.collect_compliance_evidence("SHP-000001")

    assert result["success"] is True
    assert result["collection_errors"] == []
    assert result["source_results"]
    shipment_source = next(
        source for source in result["source_results"]
        if source["source_name"] == "shipment"
    )
    assert shipment_source["status"] == EvidenceSourceStatus.SUCCESS.value
    assert shipment_source["provenance"]["dataset"] == "shipments.csv"
    assert shipment_source["provenance"]["query"] == {
        "shipment_id": "SHP-000001",
    }
    assert "SHP-000001" in shipment_source["provenance"]["record_ids"]


def test_compliance_evidence_preserves_source_level_errors(monkeypatch):
    monkeypatch.setattr(
        evidence_tools,
        "get_label_artworks",
        lambda *args, **kwargs: {
            "success": False,
            "error": "label source unavailable",
        },
    )

    result = evidence_tools.collect_compliance_evidence("SHP-000001")

    assert result["success"] is True
    errors = [
        source for source in result["source_results"]
        if source["source_name"] == "label_artworks"
    ]
    assert len(errors) == 1
    assert errors[0]["status"] == EvidenceSourceStatus.ERROR.value
    assert errors[0]["error"] == "label source unavailable"
    assert errors[0]["provenance"]["dataset"] == "label_artworks.csv"
    assert errors[0] in result["collection_errors"]


def test_document_field_failure_is_not_hidden(monkeypatch):
    monkeypatch.setattr(
        document_tools,
        "get_shipment_documents",
        lambda shipment_id: {
            "success": True,
            "documents": [{"document_id": "DOC-1"}],
        },
    )
    monkeypatch.setattr(
        document_tools,
        "get_document_fields",
        lambda document_ids: {
            "success": False,
            "error": "extraction source unavailable",
        },
    )

    result = document_tools.get_shipment_document_evidence("SHP-1")

    assert result["success"] is False
    assert "extraction source unavailable" in result["error"]


@pytest.mark.parametrize(
    ("module_name", "expected_name", "expected_port"),
    [
        ("freight_agent.agent", "freight_quote_agent", 8001),
        ("compliance_agent.agent", "apparel_compliance_agent", 8002),
    ],
)
def test_specialist_a2a_contract(module_name, expected_name, expected_port):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        module = __import__(module_name, fromlist=["a2a_app"])

    with TestClient(module.a2a_app) as client:
        card_response = client.get("/.well-known/agent-card.json")

        assert card_response.status_code == 200
        card = card_response.json()
        assert card["name"] == expected_name
        assert card["supportedInterfaces"] == [{
            "url": f"http://localhost:{expected_port}",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0",
        }]
        assert any(
            route.path == "/" and "POST" in route.methods
            for route in module.a2a_app.routes
        )
