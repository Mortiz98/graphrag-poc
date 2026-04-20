# AGENTS.md

## Project
GraphRAG PoC — Hybrid RAG system (Qdrant + NebulaGraph + Google ADK) con FastAPI y Streamlit.

## Commands
```bash
make run            # Docker + schema + API + Streamlit
make test           # lint + format + tests
make stop           # stop Docker
make clean          # remove volumes + caches
make seed           # load sample.txt
make init           # init NebulaGraph schema
```

## Required order
```bash
uv run ruff check app/ tests/ evals/ ui/ && uv run ruff format app/ tests/ evals/ ui/ && uv run pytest tests/ -v
```

## Environment
- `.env` (gitignored): set `GEMINI_API_KEY`
- Runtime: Google ADK + Gemini (single stack)
- LLM: `gemini-2.5-flash`
- Embeddings: `text-embedding-004` (768d)
- Qdrant collection: `triplets`
- NebulaGraph space: `graphrag`

## Key gotchas

**Google GenAI:**
- `app/core/genai.py` is the single LLM+embedding client — all generation and embedding goes through here
- Thread-safe singleton via `get_genai_client()`
- Embedding batch size: 20, dimensions: 768
- `llm.py` and `embeddings.py` are DEPRECATED legacy wrappers — do not use for new code
- Pipelines use `genai.generate()` and `genai.generate_stream()` directly (no dual LLM path)

**NebulaGraph:**
- Use `.get_sVal().decode()` for strings, not `.as_string()`
- Vertex IDs: `_sanitize_vertex_id()` sanitizes names (max 256 chars, alphanumeric + underscore + hash suffix)
- `index` is reserved — use `chunk_index`
- `timestamp` is reserved in nGQL — use `reported_at` instead
- Domain schema routing: `ENTITY_TYPE_TO_TAG` maps subject_type → tag, `PREDICATE_TO_EDGE` maps predicate → edge
- `store_in_graph` uses domain tags/edges with fallback to `entity`/`related_to` on failure
- `expand_from_graph` iterates ALL edge types (16 domain edges), supports `relation_types` filter
- 4 tags: entity, issue, stakeholder, commitment; 17 edges (16 domain + related_to fallback)

**Qdrant:**
- Use `query_points()`, not `search()` (v1.17+)
- Collection auto-created on first ingestion
- Vector size: 768 (not 1536)
- `get_qdrant_client()` is a thread-safe singleton (with `reset_qdrant_client()`)
- 14 payload indexes: source_doc, chunk_id, subject_id, object_id, system, account_id, tenant_id, user_id, is_active, fact_type, memory_type, product, version, severity, channel
- `_ensure_payload_indexes()` silently swallows all exceptions — check logs if indexes seem missing
- `active_only=True` by default in queries — filters `is_active=True` to exclude superseded facts

**Google ADK:**
- Agents defined in `app/agents/`
- Tools in `app/agents/tools/`
- Model configured via `app/agents/base.py` — defaults to Gemini
- `InMemorySessionService` — sessions lost on restart
- `InMemoryArtifactService` and `InMemoryMemoryService` ARE wired into Runner
- `state_delta` used to inject account_id into AM agent
- Support agent has 6 tools: `search_knowledge_base`, `search_by_metadata`, `search_by_product`, `get_resolution_history`, `escalation_path`, `traverse_issue_graph`
- AM agent has 10 tools: 6 read + 4 write (write_fact, update_fact, write_commitment, write_stakeholder)
- Part attributes use snake_case: `function_call`, `function_response` (not camelCase)

**Consolidation:**
- `run_consolidation_pipeline()` results ARE applied — surviving keys filter original triplets before store
- `skip_dedup=False` by default — dedup enabled
- Memory types: state, episodic, semantic, procedural
- `apply_supersession()` marks old facts with `valid_to`, `is_active=False`, `superseded_by`

**Account Tools:**
- `get_account_state` uses `AccountStore` (structured object), not synthetic queries
- `get_commitments`, `get_stakeholder_map` use `search_by_filter` (structured filtering, no embedding)
- AM agent HAS write tools — `write_fact`, `update_fact`, `write_commitment`, `write_stakeholder`
- `memory_writer` only writes to Qdrant — no NebulaGraph writes yet

**Evaluation:**
- `support_qa.jsonl` has 25 questions in Spanish based on sample.txt support domain
- `ideal_answers` aligned to current Gemini/768d stack
- `relevant_chunks` populated post-ingest via `evals/populate_chunks.py`
- `relevant_keywords` extracted from sample.txt content
- `am_continuity.jsonl` exists but no runner can process its schema yet

**Streamlit:**
- Requires `PYTHONPATH=.` to import `ui.*` modules
- Query page uses agent endpoints (`/agents/support/query`, `/agents/am/query`)
- Session IDs stored in `st.session_state.agent_session_ids`
- Upload page exposes metadata: System selector, Tenant ID, Account ID (AM only), Case Metadata expander (Product, Version, Severity, Channel)

**Traces:**
- Each retrieval tool calls `engine.log_trace()` with phase `tool:<name>` after each retrieval operation
- Agent endpoints log overall interaction trace with phase `agent:<name>`, including tool calls, duration, session_id
- `_extract_tool_calls()` extracts function_call/function_response from ADK events (snake_case attributes)
- Traces persisted as JSONL files in `traces/` directory

## Testing
- 228 tests + 2 skipped across 14 files
- 8 integration tests fail without Docker, 2 skipped
- Unit tests use mocks, no Docker needed
- Test coverage for: domain routing in store_in_graph, build_vertex_insert, build_edge_insert, search_by_filter, all 6 retrieval tools, extract_tool_calls, log_interaction
- `apply_supersession()` always mocked — never tested directly
- Run evals: `PYTHONPATH=. uv run python -c "from evals.runner import run_retrieval_eval; print(run_retrieval_eval('evals/truth_sets/support_qa.jsonl'))"`

## PRD Phases
- Etapa 0: COMPLETE — Platform base, ADK runtime, retrieval abstraction, namespaces, consolidation, evaluation framework
- Etapa 1A: COMPLETE — MVP Soporte (domain graph in ingest, grounded responses, 6 tools, traces, truth set 25 questions, UI metadata)
- Etapa 1B: ~40% — MVP Account Manager (write tools + AccountStore exist, need graph writes, domain prompt, eval runner, artifact tools)
- Etapa 2-5: Not started
- See `docs/PRD.md` for full plan

## API Endpoints
```
/api/v1/ingest                     - upload document
/api/v1/seed                       - load sample.txt
/api/v1/query                      - sync query (direct pipeline, active_only=True default)
/api/v1/query/stream               - streaming query (SSE)
/api/v1/documents                  - list/delete
/api/v1/health                     - health check
/api/v1/graph/*                    - graph queries
/api/v1/traces/*                   - retrieval traces
/api/v1/artifacts/*                - artifact management (prompts, playbooks)
/api/v1/agents/support/query       - support agent (ADK-orchestrated)
/api/v1/agents/support/query/stream- support agent streaming
/api/v1/agents/am/query            - AM agent (ADK-orchestrated)
/api/v1/agents/am/query/stream     - AM agent streaming
/api/v1/agents/am/state/{id}       - account state
```

## Architecture
```
app/
  agents/               - Google ADK agents (support, account_manager)
    artifacts.py        - InMemoryArtifactService (wired to Runner)
    prompts/            - System prompts per agent (support has domain-specific grounded format)
    tools/              - ADK tool functions (retrieval_tools: 6 tools, account_tools: 10 tools)
  api/routes/           - FastAPI endpoints
  core/                 - genai (LLM+emb singleton), retrieval, graph, vectorstore (singleton), account_store
  pipelines/            - ingestion, query, consolidation, memory_writer, loaders, text_splitter
  models/               - Pydantic schemas, Document type, graph schema (domain tags+edges+mapping dicts)
  prompts/              - Extraction prompts (generic + support-specific) and QA prompts
evals/                  - Evaluation metrics, truth sets, runner (keyword-based relevance), populate_chunks.py
ui/                     - Streamlit pages and components
```
