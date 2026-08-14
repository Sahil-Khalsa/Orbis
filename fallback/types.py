"""Core types shared across the adjudication pipeline.

Money is always integer cents. No floats, no Decimal, anywhere in this file
or anything that consumes it.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Outcome(str, Enum):
    AUTO_APPROVE = "AUTO_APPROVE"
    ROUTE_TO_HUMAN = "ROUTE_TO_HUMAN"
    BLOCK = "BLOCK"
    DEFER = "DEFER"


# Precedence, highest first. Money-relevant resolution reads this list, not
# a chain of if/elif, so the ordering can't drift out of sync.
OUTCOME_PRECEDENCE: list[Outcome] = [
    Outcome.BLOCK,
    Outcome.ROUTE_TO_HUMAN,
    Outcome.DEFER,
    Outcome.AUTO_APPROVE,
]


class DestinationType(str, Enum):
    bank = "bank"
    agent = "agent"


class PurposeClass(str, Enum):
    infrastructure = "infrastructure"
    software = "software"
    legal = "legal"
    contractor = "contractor"
    marketing = "marketing"
    travel = "travel"
    hardware = "hardware"
    other = "other"


class AgentKind(str, Enum):
    spender = "spender"
    payee = "payee"


class AgentStatus(str, Enum):
    active = "active"
    frozen = "frozen"


class VendorStatus(str, Enum):
    approved = "approved"
    pending = "pending"
    blocked = "blocked"


class WarrantStatus(str, Enum):
    active = "active"
    expired = "expired"
    revoked = "revoked"


class SpendRequestStatus(str, Enum):
    submitted = "submitted"
    decided = "decided"
    queued = "queued"
    executed = "executed"
    failed = "failed"


class DecidedBy(str, Enum):
    engine = "engine"
    reasoner = "reasoner"
    human = "human"


class RuleResult(BaseModel):
    rule_id: str  # "R1".."R6"
    outcome: Outcome
    reason_code: str  # SCREAMING_SNAKE, stable, user-visible
    detail: str
    evidence_ids: list[str] = Field(default_factory=list)


class LineItem(BaseModel):
    description: str
    amount_cents: int


class Extraction(BaseModel):
    spend_request_id: Optional[str] = None
    vendor_name_norm: str
    vendor_id_match: Optional[str] = None
    match_confidence: float = 0.0
    purpose_class: PurposeClass
    line_items: list[LineItem] = Field(default_factory=list)
    injection_flags: list[str] = Field(default_factory=list)


class Decision(BaseModel):
    id: Optional[str] = None
    spend_request_id: str
    # DEFER never persists as a final decision outcome.
    outcome: Literal["AUTO_APPROVE", "ROUTE_TO_HUMAN", "BLOCK"]
    decided_at: Optional[str] = None
    decided_by: DecidedBy
    rationale: str
    cited_rule_ids: list[str] = Field(default_factory=list)
    cited_warrant_id: Optional[str] = None
    rule_results: list[RuleResult] = Field(default_factory=list)


class SpendRequest(BaseModel):
    id: Optional[str] = None
    agent_id: str
    warrant_id: Optional[str] = None
    destination_type: DestinationType
    vendor_name_raw: Optional[str] = None
    counterparty_agent_id: Optional[str] = None
    category: str
    amount_cents: int
    business_purpose_raw: str
    submitted_at: Optional[str] = None
    status: SpendRequestStatus = SpendRequestStatus.submitted


# Reasoner return type: no approval value exists in the type. This is the
# schema enforcement invariant 1 requires -- the model literally cannot
# return an outcome that clears money.
ReasonerVerdict = Literal["ROUTE", "BLOCK", "CLEAR_DEFERRAL"]


class ReasonerOutput(BaseModel):
    verdict: ReasonerVerdict
    rationale: str
    cited_clause_id: Optional[str] = None
    cited_evidence_ids: list[str] = Field(default_factory=list)
