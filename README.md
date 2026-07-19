# ExportOps

ExportOps is an agentic shipment decision prototype for India-to-EU apparel exports.
It combines deterministic shipment, document, compliance-evidence, and freight tools
with specialist agents that interpret the evidence and a coordinator agent that produces
a shipment-level decision.

The project is designed around a strict boundary:

- tools retrieve records and perform calculations;
- specialist agents assess evidence and uncertainty;
- the coordinator combines those findings into an operational decision;
- humans remain responsible for ambiguous or consequential decisions.

The included data is synthetic and is intended for demonstrations and evaluation. It is
not a legal determination, customs guarantee, certification, or production compliance
system.

## Architecture

```text
                         +-----------------------------+
                         | Shipment Decision Coordinator|
                         | app/agent.py                |
                         +--------------+--------------+
                                        |
                 +----------------------+----------------------+
                 |                                             |
                 v                                             v
       +-----------------------+                     +-----------------------+
       | Apparel Compliance    |                     | Freight Quote         |
       | Specialist            |                     | Specialist            |
       | compliance_agent/     |                     | freight_agent/        |
       | A2A :8002             |                     | A2A :8001             |
       +-----------+-----------+                     +-----------+-----------+
                   |                                             |
                   +----------------------+----------------------+
                                          v
                              app/tools and data/*.csv
```

### Agents

#### Shipment Decision Coordinator

Location: `app/agent.py`

The coordinator establishes the shipment stage, reviews shipment and document facts,
delegates specialist analysis, considers contradictions and operational timing, and
returns one of:

- `READY_TO_PROCEED`
- `PROCEED_WITH_CONDITIONS`
- `HUMAN_REVIEW_REQUIRED`
- `BLOCKED_PENDING_EVIDENCE`
- `REJECTED`

Its output follows `ShipmentAssessment` in `app/schemas.py`.

#### Apparel Compliance Specialist

Location: `compliance_agent/agent.py`

This agent evaluates product identity, components, labels, supplier declarations,
laboratory evidence, document requirements, regulatory references, and EU economic
operator records. It must distinguish exact evidence from broad or weak matches and
must state when human verification is required.

It is exposed as an A2A service on port `8002`.

#### Freight Quote Specialist

Location: `freight_agent/agent.py`

This agent evaluates rate-card applicability, lane and mode compatibility, rate validity,
minimum charges, estimated transit, deadlines, currency comparability, and freight
trade-offs. It does not make the final shipment decision.

It is exposed as an A2A service on port `8001`.

## Tool and data layers

Tools are in `app/tools/`:

- `shipment_tools.py`: shipment, line-item, exporter, and buyer records.
- `document_tools.py`: document register records and extracted fields.
- `evidence_tools.py`: products, components, labels, declarations, lab reports,
  regulatory rules, requirements, and responsible operators.
- `freight_tools.py`: rate matching, quote calculations, and deadline facts.
- `intake_tools.py`: shipment-to-line-item totals and timeline calculations.
- `data_access.py`: shared CSV loading and identifier normalization.

The data files are in `data/`. `data/README.csv` describes the dataset scope and
limitations. Tools intentionally return raw facts and provenance rather than silently
assigning compliance or risk labels.

## Evidence citations

Agent responses must cite supplied records using stable source references, for example:

```text
The shipment has six registered documents [SRC:shipment_documents/DOC-0000002].
The rate is valid for the shipment date [SRC:freight_rates/RATE-000025].
The quote calculation includes the rate and derived total
[SRC:freight_calculations/QUOTE-RATE-000025].
```

If the supplied records do not establish a fact, the response must use:

```text
Unavailable from supplied records [SRC:UNAVAILABLE]
```

Source status and provenance are returned through `source_results`. A source with
status `ERROR` must not be treated as evidence.

## Local setup

Use Python 3.11 or newer and create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the required packages used by the project:

```powershell
pip install google-adk a2a-sdk pandas pydantic python-dotenv
```

Set the API key through the environment or an ignored local `.env` file in each agent
directory that requires it:

```text
GOOGLE_API_KEY=your-key-here
```

Never commit API keys. Rotate a key immediately if it has been committed or shared.

## Running the agents

### Docker Compose

Docker Compose runs the two A2A specialist services and the coordinator together.
Set `GOOGLE_API_KEY` in the host environment or in a root `.env` file, then run:

```powershell
docker compose up --build
```

The services are available at:

- Coordinator ADK UI: `http://localhost:8000`
- Freight agent card: `http://localhost:8001/.well-known/agent-card.json`
- Compliance agent card: `http://localhost:8002/.well-known/agent-card.json`

Stop the stack with:

```powershell
docker compose down
```

The Compose configuration uses service names for internal A2A communication, so the
coordinator can reach `freight-agent` and `compliance-agent` inside the Docker network.

Start the specialist A2A services in separate terminals from the repository root:

```powershell
python -m uvicorn freight_agent.agent:a2a_app --host 127.0.0.1 --port 8001
python -m uvicorn compliance_agent.agent:a2a_app --host 127.0.0.1 --port 8002
```

Then run the coordinator through the Google ADK development interface according to the
installed ADK version. From the repository root, the usual command is:

```powershell
adk web app
```

The coordinator expects the specialist agent cards at:

- `http://127.0.0.1:8001/.well-known/agent-card.json`
- `http://127.0.0.1:8002/.well-known/agent-card.json`

## Direct tool checks

Tools can be exercised without calling an LLM:

```powershell
python -c "from app.tools.evidence_tools import collect_compliance_evidence; print(collect_compliance_evidence('SHP-000001'))"
```

Freight matching and calculations are deterministic and can be tested independently
from the agent runtime.

## Testing and verification

Compile the project with:

```powershell
python -m compileall -q app compliance_agent freight_agent
```

Run the test suite with:

```powershell
pytest -q
```

The project is currently a prototype. Tests should be expanded to cover tool behavior,
malformed records, source-error propagation, freight calculations, citation contracts,
and A2A service responses before production use.

## Important limitations

- CSV files are used as the data store; this is not a concurrent production persistence
  layer.
- A2A support in the installed Google ADK may be experimental.
- Regulatory rows are references for reasoning and do not replace current professional
  legal or customs review.
- Agent output is constrained by prompts, provenance, and a structured coordinator
  schema, but a final citation-validation gate is still recommended before automated
  downstream action.
- No agent should independently release cargo, approve legal compliance, or override a
  human review requirement.
