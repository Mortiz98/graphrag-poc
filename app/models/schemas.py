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


class IngestRequest(BaseModel):
    filename: str = Field(..., description="Name of the uploaded file")


class IngestResponse(BaseModel):
    document_id: UUID = Field(default_factory=uuid4)
    filename: str
    chunks_count: int
    triplets_count: int
    status: str = "processed"


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="User question")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of triplets to retrieve")


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
