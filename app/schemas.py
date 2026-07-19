from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Confidence(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ApplicabilityStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    PROVISIONAL = "PROVISIONAL"
    UNCERTAIN = "UNCERTAIN"


class SpecialistOutcome(StrEnum):
    SUPPORTS_COMPLIANCE = "SUPPORTS_COMPLIANCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    HUMAN_VERIFICATION_NEEDED = "HUMAN_VERIFICATION_NEEDED"


class CoordinatorDecision(StrEnum):
    READY_TO_PROCEED = "READY_TO_PROCEED"
    PROCEED_WITH_CONDITIONS = "PROCEED_WITH_CONDITIONS"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
    BLOCKED_PENDING_EVIDENCE = "BLOCKED_PENDING_EVIDENCE"
    REJECTED = "REJECTED"


class EvidenceSourceStatus(StrEnum):
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


class ContractModel(BaseModel):
    """Shared boundary model: unknown fields are contract violations."""

    model_config = ConfigDict(extra="forbid")


class EvidenceProvenance(ContractModel):
    source_name: str
    source_kind: Literal["csv", "derived"]
    dataset: str | None = None
    query: dict[str, Any] = Field(default_factory=dict)
    record_ids: list[str] = Field(default_factory=list)


class EvidenceSourceResult(ContractModel):
    source_name: str
    status: EvidenceSourceStatus
    provenance: EvidenceProvenance
    record_count: int = 0
    error: str | None = None


class SpecialistFinding(ContractModel):
    rule_id: str
    outcome: SpecialistOutcome
    rationale: str
    confidence: Confidence


class HumanReview(ContractModel):
    required: bool
    reviewer_role: str | None = None
    questions: list[str] = Field(default_factory=list)
    override_possible: bool = False
    override_evidence: list[str] = Field(default_factory=list)


class ShipmentItem(BaseModel):
    shipment_item_id: str
    shipment_id: str
    line_number: int
    product_id: str
    product_name: str
    hs_code: str
    quantity: float
    unit: str
    unit_price_usd: float
    line_value_usd: float
    gross_weight_kg: float
    package_count: int
    volume_cbm: float


class Shipment(BaseModel):
    shipment_id: str
    shipment_date: date
    exporter_id: str
    exporter_name: str
    buyer_id: str
    buyer_name: str
    origin_city: str
    destination_country: str
    destination_port: str
    destination_unlocode: str
    preferred_transport: str
    incoterm: str
    payment_term: str
    gross_weight_kg: float
    volume_cbm: float
    package_count: int
    invoice_value_usd: float
    currency: str
    insurance_required: str
    special_handling: str
    delivery_deadline: date
    status: str
    risk_score: float
    priority: str
    agent_run_id: str


class ValidationResult(BaseModel):
    valid: bool
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ShipmentAssessment(BaseModel):
    """Canonical coordinator response shared by all shipment workflows."""

    model_config = ConfigDict(extra="forbid")

    shipment_id: str
    current_stage: str
    next_intended_action: str
    final_decision: CoordinatorDecision
    confidence: Confidence
    decision_rationale: str
    material_blockers: list[str] = Field(default_factory=list)
    conditions_to_proceed: list[str] = Field(default_factory=list)
    non_blocking_observations: list[str] = Field(default_factory=list)
    contradictions_and_uncertainties: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    human_review: HumanReview
    recommended_actions_in_order: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)


class ComplianceSpecialistAssessment(ContractModel):
    overall_specialist_outcome: SpecialistOutcome
    confidence: Confidence
    specialist_findings: list[SpecialistFinding] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)


class FreightSpecialistAssessment(ContractModel):
    confidence: Confidence
    feasible_quote_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    trade_offs: list[str] = Field(default_factory=list)
    evidence_references: list[str] = Field(default_factory=list)
