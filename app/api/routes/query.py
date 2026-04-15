from fastapi import APIRouter

from app.models.schemas import QueryRequest, QueryResponse
from app.pipelines.query import query as query_pipeline

router = APIRouter(prefix="/api/v1", tags=["query"])


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    return query_pipeline(request.question, request.top_k)
