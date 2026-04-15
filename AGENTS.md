# AGENTS.md

## Project overview

GraphRAG PoC — a hybrid RAG system that combines vector search (Qdrant) with graph traversal (NebulaGraph) for answering questions over ingested documents, with a Streamlit UI for visualization and interaction.

## Dev commands

```bash
make run                         # start everything (Docker + API + Streamlit)
make test                        # lint + format + run all tests
make stop                        # stop Docker services
make clean                       # full reset (deletes Docker volumes)
make seed                        # load sample data
make init                        # initialize NebulaGraph schema
```

Manual alternatives:

```bash
uv sync                          # install dependencies
uv sync --extra dev              # install dev deps (pytest, ruff)
uv run ruff check --fix app/ tests/ ui/  # lint
uv run ruff format app/ tests/ ui/       # format
uv run pytest tests/ -v                  # run all tests (108 unit + integration)
```

## Required order before commits

```bash
uv run ruff check app/ tests/ ui/ && uv run ruff format app/ tests/ ui/ && uv run pytest tests/ -v
```

Lint/format must pass before committing. Tests require Docker services running (Qdrant + NebulaGraph) and a valid `OPENROUTER_API_KEY` in `.env`.

## Infrastructure prerequisites

Docker services must be running before any runtime or integration test:

```bash
docker compose up -d
```

NebulaGraph schema must be initialized after first startup or after `docker compose down -v`:

```bash
make init
```

There is a **5-second sleep** between `CREATE SPACE` and `USE graphrag` in `scripts/init_nebula.py` — NebulaGraph needs this delay for async space creation.

## Environment

- `.env` holds secrets (gitignored). Copy `.env.example` to `.env` and set `OPENROUTER_API_KEY`.
- Settings loaded via pydantic-settings (`app/config.py`). All env vars have defaults except the API key.
- Default models: `openai/gpt-4o-mini` (LLM), `openai/text-embedding-3-small` (embeddings, 1536d).
- Qdrant collection hardcoded as `triplets` (1536d cosine). NebulaGraph space is `graphrag`.

## NebulaGraph gotchas

- Docker uses custom `config/nebula/*.conf` files. `local_ip` must match the Docker service name (e.g., `nebula-metad`, `nebula`, `nebula-storaged`), **not** `127.0.0.1`.
- `nebula3-python` API: use `.get_sVal().decode()` for string values in query results, **not** `.as_string()`.
- `index` is a reserved keyword in nGQL — use `chunk_index` instead.
- `ADD HOSTS IF NOT EXISTS` is not valid nGQL v3 — just use `ADD HOSTS`.
- Vertex IDs: `_sanitize_vertex_id()` converts entity names to valid NebulaGraph VIDs (alphanumeric + underscore only, max 256 chars).

## Qdrant gotchas

- The client uses `query_points()` (not `search()`) — this was changed for qdrant-client v1.17+.
- Collection is auto-created on first ingestion if it doesn't exist (`ensure_collection_exists` in `vectorstore.py`).
- Payload indexes on `source_doc`, `chunk_id`, `subject_id`, `object_id` are created automatically.

## Architecture

```
app/
  main.py              # FastAPI app entrypoint
  config.py            # pydantic-settings (env vars)
  api/routes/          # HTTP endpoint handlers
    health.py          # GET /api/v1/health
    ingest.py          # POST /api/v1/ingest
    query.py           # POST /api/v1/query
    documents.py       # GET /documents, DELETE /documents/{filename}, GET /graph/stats
  api/exceptions.py   # Custom HTTP exceptions
  core/                # Service wrapper clients
    llm.py             # ChatOpenAI via OpenRouter
    embeddings.py      # OpenAIEmbeddings via OpenRouter
    graph.py           # NebulaGraph singleton connection pool (context manager)
    vectorstore.py      # Qdrant client + collection init + payload indexes
  pipelines/
    ingestion.py       # Full pipeline: load → chunk → extract → graph + vectors
    query.py            # Full pipeline: embed → search → traverse → fuse → LLM
    loaders.py          # PDF/TXT/MD file loaders
  models/
    schemas.py          # Pydantic request/response models (Triplet uses alias="object")
    graph_schema.py     # NebulaGraph tag/edge name constants
  prompts/
    extraction.py       # LLM prompt for entity/relation extraction
    qa.py               # LLM prompt for question answering
ui/
  app.py                 # Streamlit entrypoint (multipage)
  pages/
    1_Upload.py          # Document upload page
    2_Graph.py           # Graph explorer (placeholder)
    3_Query.py           # Chat & query interface
    4_Documents.py       # Document management
  components/
    api_client.py        # httpx REST client for FastAPI
    sidebar.py           # Shared sidebar with service health
```

## Key conventions

- **All code, comments, and docs in English** — no Spanish anywhere.
- No comments unless asked for — code should be self-documenting.
- Pydantic `Triplet` model uses `Field(alias="object")` because `object` is a Python keyword.
- Logging: `structlog` everywhere, never `print()`.
- FastAPI `TestClient` for integration tests (not `uvicorn` subprocess).
- The `.env` file **must never** be committed.

## Testing

- Integration tests in `tests/test_api.py` hit live services (Qdrant, NebulaGraph, OpenRouter). They require Docker running and a valid API key.
- Unit tests (`test_schemas.py`, `test_loaders.py`, `test_ingestion.py`, `test_query.py`, `test_core.py`, `test_vectorstore.py`, `test_api_client.py`) are pure Python with mocks and need no services.
- Unit tests cover: schema validation, loaders, chunking, triplet extraction, graph/vector storage, graph traversal, context fusion, confidence scoring, connection pooling, health checks, API client.
- Integration tests make real API calls (no LLM mocks).

## Running the system

```bash
make run
```

- FastAPI at `http://localhost:8000` — Swagger UI at `/docs`
- Streamlit at `http://localhost:8501` — main UI
