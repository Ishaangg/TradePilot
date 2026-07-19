from pathlib import Path

from dotenv import load_dotenv
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent

from app.tools.document_tools import (
    get_document_fields,
    get_shipment_document_evidence,
    get_shipment_documents,
)
from app.tools.evidence_tools import (
    collect_compliance_evidence,
    get_document_requirements,
    get_label_artworks,
    get_product_context,
    get_product_lab_evidence,
    get_regulatory_rules,
    get_responsible_operator,
    get_supplier_declarations,
)
from app.tools.shipment_tools import (
    get_shipment,
    get_shipment_items,
    get_shipment_parties,
)


ENV_FILE = Path(__file__).resolve().parent / ".env"
PROMPT_FILE = (
    Path(__file__).resolve().parents[1]
    / "prompts"
    / "apparel_compliance_specialist.md"
)

load_dotenv(ENV_FILE, override=True)


def load_instruction() -> str:
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(
            f"Compliance agent prompt was not found: {PROMPT_FILE}"
        )

    return PROMPT_FILE.read_text(encoding="utf-8")


root_agent = Agent(
    name="apparel_compliance_agent",
    model="gemini-2.5-flash",
    description=(
        "Analyzes raw India-to-EU apparel compliance evidence, "
        "including product construction, textile labels, supplier "
        "declarations, laboratory reports, economic-operator records, "
        "customs documents, and regulatory requirements."
    ),
    instruction=load_instruction(),
    tools=[
        collect_compliance_evidence,
        get_shipment,
        get_shipment_items,
        get_shipment_parties,
        get_product_context,
        get_shipment_documents,
        get_document_fields,
        get_shipment_document_evidence,
        get_label_artworks,
        get_supplier_declarations,
        get_product_lab_evidence,
        get_responsible_operator,
        get_regulatory_rules,
        get_document_requirements,
    ],
)


a2a_app = to_a2a(
    root_agent,
    host="0.0.0.0",
    port=8002,
)
