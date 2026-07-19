import os
from pathlib import Path

from google.adk.agents import Agent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

from app.schemas import ShipmentAssessment
from app.tools.document_tools import (
    get_shipment_document_evidence,
)
from app.tools.intake_tools import (
    compare_shipment_totals,
    get_timeline_facts,
)
from app.tools.shipment_tools import (
    get_shipment,
    get_shipment_items,
    get_shipment_parties,
)


PROMPT_FILE = (
    Path(__file__).resolve().parents[1]
    / "prompts"
    / "shipment_decision_coordinator.md"
)


def load_instruction() -> str:
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(
            f"Coordinator prompt was not found: {PROMPT_FILE}"
        )

    return PROMPT_FILE.read_text(encoding="utf-8")


freight_quote_agent = RemoteA2aAgent(
    name="freight_quote_agent",
    description=(
        "Analyzes raw freight rate cards, calculates estimated costs, "
        "checks validity and deadline feasibility, and explains "
        "freight trade-offs."
    ),
    agent_card=(
        os.getenv(
            "FREIGHT_AGENT_CARD",
            "http://127.0.0.1:8001/.well-known/agent-card.json",
        )
    ),
    use_legacy=False,
)


apparel_compliance_agent = RemoteA2aAgent(
    name="apparel_compliance_agent",
    description=(
        "Analyzes raw India-to-EU apparel compliance evidence, "
        "including products, components, labels, declarations, "
        "laboratory reports, documents, and regulatory requirements."
    ),
    agent_card=(
        os.getenv(
            "COMPLIANCE_AGENT_CARD",
            "http://127.0.0.1:8002/.well-known/agent-card.json",
        )
    ),
    use_legacy=False,
)


root_agent = Agent(
    name="shipment_decision_coordinator",
    model="gemini-2.5-flash",
    description=(
        "Coordinates shipment intake, apparel compliance, freight, "
        "documents, and human-review requirements to produce the "
        "final shipment-level inference."
    ),
    instruction=load_instruction(),
    output_schema=ShipmentAssessment,
    tools=[
        get_shipment,
        get_shipment_items,
        get_shipment_parties,
        get_shipment_document_evidence,
        compare_shipment_totals,
        get_timeline_facts,
    ],
    sub_agents=[
        apparel_compliance_agent,
        freight_quote_agent,
    ],
)
