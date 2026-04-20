import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.agents import router as agents_router
from app.api.routes.artifacts import router as artifacts_router
from app.api.routes.documents import router as documents_router
from app.api.routes.graph import router as graph_router
from app.api.routes.health import router as health_router
from app.api.routes.ingest import router as ingest_router
from app.api.routes.query import router as query_router
from app.api.routes.traces import router as traces_router
from app.config import get_settings

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(20),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

app = FastAPI(
    title="GraphRAG PoC",
    version="0.1.0",
    description="""
Hybrid RAG system combining vector search (Qdrant), knowledge graph (NebulaGraph), and LLM generation.

## Systems

- **Sistema A (Support)**: Qdrant-first retrieval with case metadata (product, version, severity)
- **Sistema B (Account Manager)**: Longitudinal memory with facts, episodes, commitments, and temporal validity

## Endpoints

### Ingestion
- **POST /api/v1/ingest** — Upload document (PDF/TXT/MD) with optional case/fact metadata
- **POST /api/v1/seed** — Load sample.txt into knowledge base

### Query
- **POST /api/v1/query** — Sync Q&A with grounded sources
- **POST /api/v1/query/stream** — Streaming Q&A (SSE)

### Documents
- **GET /api/v1/documents** — List all documents
- **DELETE /api/v1/documents/{filename}** — Delete document and its data

### Graph
- **GET /api/v1/graph/stats** — Graph statistics
- **GET /api/v1/graph/entities** — All entities with degrees
- **GET /api/v1/graph/edges** — All edges
- **GET /api/v1/graph/subgraph** — N-hop neighborhood
- **GET /api/v1/graph/filters** — Available filter values

### Traces
- **GET /api/v1/traces** — List retrieval traces
- **GET /api/v1/traces/{trace_id}** — Get trace details
- **GET /api/v1/traces/search** — Search traces by query

### Agents (ADK)
- **POST /api/v1/agents/support/query** — Support agent (grounded Q&A)
- **POST /api/v1/agents/am/query** — Account Manager agent (continuity)

### Artifacts
- **GET /api/v1/artifacts** — List saved playbooks/prompts
- **POST /api/v1/artifacts** — Save artifact

### Health
- **GET /api/v1/health** — Health check for all services
    """,
)


@app.on_event("startup")
async def validate_configuration():
    """Validate critical configuration on startup."""
    settings = get_settings()
    settings.validate_api_key()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(query_router)
app.include_router(documents_router)
app.include_router(graph_router)
app.include_router(agents_router)
app.include_router(traces_router)
app.include_router(artifacts_router)


def run_server() -> None:
    import uvicorn

    from app.config import get_settings

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
