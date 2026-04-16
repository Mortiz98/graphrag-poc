# GraphRAG PoC

Hybrid RAG system with Google ADK, Qdrant and NebulaGraph. Two agentive memory systems: Virtual Support and Account Manager.

## Systems

| System | Purpose |
|--------|---------|
| **A (Support)** | Knowledge base with product/version filters, grounded responses |
| **B (Account Manager)** | Longitudinal memory: facts, episodes, commitments, continuity |

## Architecture

```
make run
├── Docker (Qdrant + NebulaGraph)
├── FastAPI :8000 (REST API)
└── Streamlit :8501 (UI)
       │
       ▼
   ┌─────────┬──────────┬──────────┐
   │ Upload  │  Graph   │  Query  │
   └────┬────┴────┬──────┴────┬─────┘
        └─────────┼───────────┘
                  ▼
             FastAPI
                  │
      ┌───────────┼───────────┐
      ▼           ▼           ▼
   Qdrant     NebulaGraph   OpenRouter
   (vectors)  (graph)     (LLM+Emb)
      │
      ▼
   Google ADK
   (agents)
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.10+
- [uv](https://docs.astral.sh/uv/)

### 1. Clone and configure

```bash
git clone https://github.com/Mortiz98/graphrag-poc.git
cd graphrag-poc
cp .env.example .env
# Edit .env: add OPENROUTER_API_KEY or GEMINI_API_KEY
```

### 2. Install

```bash
uv sync
```

### 3. Start

```bash
make run
```

- **Streamlit UI**: http://localhost:8501
- **API docs**: http://localhost:8000/docs

### 4. Load sample data

```bash
make seed
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/ingest` | Upload document (PDF/TXT/MD) |
| `POST` | `/api/v1/seed` | Load sample.txt |
| `POST` | `/api/v1/query` | Sync query |
| `POST` | `/api/v1/query/stream` | Streaming query (SSE) |
| `GET` | `/api/v1/documents` | List documents |
| `DELETE` | `/api/v1/documents/{filename}` | Delete document |
| `GET` | `/api/v1/graph/*` | Graph endpoints |
| `GET` | `/api/v1/traces/*` | Retrieval traces |
| `POST` | `/api/v1/agents/support/query` | Support agent (ADK) |
| `POST` | `/api/v1/agents/am/query` | Account Manager agent (ADK) |

## Development Phases

| Phase | Status | Description |
|------|--------|-------------|
| 0 | ✅ | Base platform, ADK, retrieval, evals |
| 1A | 🔄 | MVP Support (grounded responses) |
| 1B | ⏳ | MVP Account Manager (continuity) |
| 2 | ⏳ | Sparse + hybrid + reranking |
| 3A/3B | ⏳ | Domain and temporal graphs |
| 4-5 | ⏳ | Experiments and scaling |

## How It Works

### Ingestion

1. **Load** — PDF/TXT/MD
2. **Chunk** — RecursiveCharacterTextSplitter (1000 chars, 200 overlap)
3. **Extract** — LLM extracts triplets (subject → predicate → object)
4. **Store graph** — Entities and relations in NebulaGraph
5. **Store vectors** — Triplets embedded in Qdrant

### Query

1. **Embed question** → vector
2. **Dense search** — Qdrant top-K
3. **Graph expansion** — NebulaGraph expands context
4. **Fuse** — Deduplicate results
5. **Generate** — LLM produces answer

## Configuration (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | — | OpenRouter key |
| `GEMINI_API_KEY` | — | Google Gemini key (optional) |
| `OPENROUTER_LLM_MODEL` | `openai/gpt-4o-mini` | LLM |
| `OPENROUTER_EMBEDDING_MODEL` | `text-embedding-3-small` | Embeddings (1536d) |
| `QDRANT_HOST` | `localhost` | Qdrant |
| `NEBULA_HOST` | `localhost` | NebulaGraph |
| `NEBULA_SPACE` | `graphrag` | Space name |

## Project Structure

```
graphrag-poc/
├── Makefile
├── docker-compose.yml
├── app/
│   ├── main.py
│   ├── config.py
│   ├── agents/          # Google ADK agents
│   ├── api/routes/
│   ├── core/           # LLM, embeddings, graph, vectorstore, retrieval
│   ├── pipelines/       # ingestion, query, consolidation
│   └── models/
├── evals/              # metrics and truth sets
├── ui/                 # Streamlit pages
└── tests/              # 199 tests
```

## Tests

```bash
make test
# or: uv run pytest tests/ -v
```

## Evaluation

```bash
python -c "from evals.runner import run_retrieval_eval; print(run_retrieval_eval('evals/truth_sets/support_qa.jsonl'))"
```