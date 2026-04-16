# AGENTS.md

## Project
GraphRAG PoC — Hybrid RAG system (Qdrant + NebulaGraph + Google ADK) con FastAPI y Streamlit.

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
uv run ruff check app/ tests/ evals/ && uv run ruff format app/ tests/ evals/ && uv run pytest tests/ -v
```

## Environment
- `.env` (gitignored): set `OPENROUTER_API_KEY` and/or `GEMINI_API_KEY`
- Default LLM: `openai/gpt-4o-mini` (via OpenRouter) or `gemini-2.0-flash` (via Google ADK)
- Default embeddings: `text-embedding-3-small` (1536d)
- Qdrant collection: `triplets`
- NebulaGraph space: `graphrag`

## Key gotchas

**NebulaGraph:**
- Use `.get_sVal().decode()` for strings, not `.as_string()`
- Vertex IDs: `_sanitize_vertex_id()` sanitizes names (max 256 chars, alphanumeric + underscore)
- `index` is reserved — use `chunk_index`

**Qdrant:**
- Use `query_points()`, not `search()` (v1.17+)
- Collection auto-created on first ingestion

**Google ADK:**
- Agents defined in `app/agents/`
- Tools in `app/agents/tools/`
- Model configured via `app/agents/base.py` — defaults to Gemini

**Streamlit:**
- Requires `PYTHONPATH=.` to import `ui.*` modules

## Testing
- 199 tests pass, 2 skipped (seed tests require services)
- Unit tests use mocks, no Docker needed
- Run evals: `python -c "from evals.runner import run_retrieval_eval; print(run_retrieval_eval('evals/truth_sets/support_qa.jsonl'))"`

## PRD Phases
- Fase 0: ✅ Complete — Platform base, ADK, retrieval abstraction, evaluation
- Fase 1A: MVP Soporte — In progress
- Fase 1B: MVP Account Manager — Pending

## API Endpoints
```
/api/v1/ingest           - upload document
/api/v1/seed            - load sample.txt
/api/v1/query            - sync query
/api/v1/query/stream     - streaming query (SSE)
/api/v1/documents       - list/delete
/api/v1/health          - health check
/api/v1/graph/*         - graph queries
/api/v1/traces/*        - retrieval traces
/api/v1/agents/*        - ADK agent endpoints
```

## Architecture
```
app/
  agents/               - Google ADK agents (support, account_manager)
  api/routes/          - FastAPI endpoints
  core/                - LLM, embeddings, graph, vectorstore, retrieval
  pipelines/           - ingestion, query, consolidation
  models/              - Pydantic schemas
evals/                  - evaluation metrics, truth sets, runner
ui/                    - Streamlit pages and components
```