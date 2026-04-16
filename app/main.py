import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.documents import router as documents_router
from app.api.routes.graph import router as graph_router
from app.api.routes.health import router as health_router
from app.api.routes.ingest import router as ingest_router
from app.api.routes.query import router as query_router
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
    description="""
Knowledge graph + vector search hybrid RAG system.

## Endpoints

- **POST /api/v1/ingest** — Upload a document (PDF/TXT/MD) for processing
- **POST /api/v1/query** — Ask a question and get an answer with sources
- **GET /api/v1/documents** — List ingested documents
- **DELETE /api/v1/documents/{filename}** — Delete a document and its data
- **GET /api/v1/graph/stats** — Get knowledge graph statistics
- **GET /api/v1/health** — Health check for all services
    """,
    version="0.1.0",
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
