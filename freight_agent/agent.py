import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import Agent

from app.tools.freight_tools import (
    analyze_freight_options,
    calculate_freight_quotes,
    get_matching_freight_rates,
)
from app.tools.shipment_tools import get_shipment


ENV_FILE = Path(__file__).resolve().parent / ".env"
PROMPT_FILE = (
    Path(__file__).resolve().parents[1]
    / "prompts"
    / "freight_quote_specialist.md"
)

load_dotenv(ENV_FILE, override=True)

if not os.getenv("GOOGLE_API_KEY"):
    raise RuntimeError(
        "GOOGLE_API_KEY was not loaded. "
        f"Expected env file at: {ENV_FILE}"
    )


def load_instruction() -> str:
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(
            f"Freight Agent prompt was not found: {PROMPT_FILE}"
        )

    return PROMPT_FILE.read_text(encoding="utf-8")


root_agent = Agent(
    name="freight_quote_agent",
    model="gemini-2.5-flash",
    description=(
        "Analyzes raw freight rate cards for India-to-EU apparel "
        "shipments, calculates estimated costs, checks validity and "
        "deadline feasibility, and explains the available trade-offs."
    ),
    instruction=load_instruction(),
    tools=[
        get_shipment,
        get_matching_freight_rates,
        calculate_freight_quotes,
        analyze_freight_options,
    ],
)


a2a_app = to_a2a(
    root_agent,
    host="0.0.0.0",
    port=8001,
)
