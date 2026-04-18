# AGENTS.md

## Project
GraphRAG PoC — Hybrid RAG system (Qdrant + NebulaGraph) with Streamlit UI for document ingestion, graph visualization, and Q&A.

## Commands
```bash
make run            # Docker + API + Streamlit (requires PYTHONPATH=.)
make test           # lint + format + tests
make stop           # stop Docker
make clean          # remove volumes + caches
make seed           # load sample.txt
make init           # init NebulaGraph schema
```

## Required order
```bash
uv run ruff check app/ tests/ ui/ && uv run ruff format app/ tests/ ui/ && uv run pytest tests/ -v
```

## Environment
- `.env` (gitignored): set `OPENROUTER_API_KEY`
- Default model: `openai/gpt-4o-mini`
- Qdrant collection: `triplets` (1536d cosine)
- NebulaGraph space: `graphrag`

## Key gotchas

**NebulaGraph:**
- Use `.get_sVal().decode()` for strings, not `.as_string()`
- Vertex IDs: `_sanitize_vertex_id()` sanitizes names (max 256 chars, alphanumeric + underscore)
- `index` is reserved — use `chunk_index`

**Qdrant:**
- Use `query_points()`, not `search()` (v1.17+)
- Collection auto-created on first ingestion

**Streamlit:**
- Requires `PYTHONPATH=.` to import `ui.*` modules
- Run from project root: `cd /home/mortiz/projects/graphrag-poc && PYTHONPATH=. uv run streamlit run ui/app.py`

## API Endpoints
```
/api/v1/ingest     - upload document
/api/v1/seed       - load sample.txt
/api/v1/query      - sync query
/api/v1/query/stream - streaming query (SSE)
/api/v1/documents  - list/delete
/api/v1/graph/stats
/api/v1/graph/entities
/api/v1/graph/edges
/api/v1/graph/subgraph?entity=X&hops=N
/api/v1/graph/filters
/api/v1/agents/support/query - support agent sync query
/api/v1/agents/am/query     - AM agent sync query
/api/v1/agents/am/state/{id} - AM agent session state
/api/v1/agents/sessions     - create/list/delete sessions
```

## Architecture
```
app/
  api/routes/    - FastAPI endpoints
  core/         - LLM, embeddings, graph, vectorstore
  pipelines/    - ingestion, query
  models/       - Pydantic schemas
ui/
  pages/        - Streamlit multipage (Upload, Graph, Query, Documents)
  components/   - api_client, sidebar, graph_renderer
```

## Testing
- 126 tests pass, 2 skipped (seed tests require services)
- Unit tests use mocks, no Docker needed
- Integration tests require Docker + API key

## Running
```bash
make run
```
- API: http://localhost:8000/docs
- UI: http://localhost:8501