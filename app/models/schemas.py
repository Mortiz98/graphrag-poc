"""Pydantic models for API request/response schemas."""

from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Triplet(BaseModel):
    subject: str = Field(..., description="Subject entity name")
    subject_type: str = Field(default="entity", description="Subject entity type")
    predicate: str = Field(..., description="Relationship between subject and object")
    object: str = Field(..., alias="object", description="Object entity name")
    object_type: str = Field(default="entity", description="Object entity type")

    model_config = {"populate_by_name": True}


class CaseMetadata(BaseModel):
    tenant_id: str | None = None
    case_id: str | None = None
    product: str | None = None
    version: str | None = None
    severity: str | None = None
    channel: str | None = None
    team: str | None = None
    status: str | None = None


class FactMetadata(BaseModel):
    tenant_id: str | None = None
    account_id: str | None = None
    user_id: str | None = None
    fact_type: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    supersedes: str | None = None
    stakeholder: str | None = None
    confidence: float | None = None


class SessionMetadata(BaseModel):
    """Metadata for ADK session context."""

    tenant_id: str | None = None
    account_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None


class IngestRequest(BaseModel):
    filename: str = Field(..., description="Name of the uploaded file")
    system: str = Field(default="support", description="Target system: 'support' or 'am'")
    tenant_id: str | None = Field(default=None, description="Tenant ID for multi-tenant isolation")
    user_id: str | None = Field(default=None, description="User ID for namespace isolation")
    case_metadata: CaseMetadata | None = None
    fact_metadata: FactMetadata | None = None


class IngestResponse(BaseModel):
    document_id: UUID = Field(default_factory=uuid4)
    filename: str
    chunks_count: int
    triplets_count: int
    status: str = "processed"


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="User question")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of triplets to retrieve")
    filters: dict | None = Field(default=None, description="Optional metadata filters (e.g., source_doc, entity_type)")
    min_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Minimum similarity score threshold for vector search"
    )
    scope: dict | None = Field(default=None, description="Namespace scope: system, tenant_id, account_id, etc.")
    tenant_id: str | None = Field(default=None, description="Tenant ID for multi-tenant isolation")
    account_id: str | None = Field(default=None, description="Account ID for Sistema B (AM) queries")
    active_only: bool = Field(default=True, description="Exclude superseded facts from results")
    user_id: str | None = Field(default=None, description="User ID for namespace isolation")


class SourceTriplet(BaseModel):
    subject: str
    predicate: str
    object: str


class SourceInfo(BaseModel):
    chunk_id: str
    document: str
    triplets: list[SourceTriplet]


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceInfo] = Field(default_factory=list)
    entities_found: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DocumentInfo(BaseModel):
    id: str
    filename: str
    chunks_count: int
    triplets_count: int


class GraphStats(BaseModel):
    entity_count: int
    edge_count: int
    space: str


class StakeholderEntry(BaseModel):
    name: str
    role: str = ""
    last_seen: str = ""


class CommitmentEntry(BaseModel):
    description: str
    owner: str = ""
    due_date: str = ""
    status: str = "open"
    fact_id: str = ""


class AccountState(BaseModel):
    account_id: str
    tenant_id: str | None = None
    stakeholders: list[StakeholderEntry] = Field(default_factory=list)
    objectives: list[str] = Field(default_factory=list)
    products_of_interest: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    commitments: list[CommitmentEntry] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    last_interaction: str = ""
    last_updated: str = ""
