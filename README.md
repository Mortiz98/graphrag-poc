# GraphRAG PoC

Knowledge graph + vector search hybrid RAG system with an interactive Streamlit UI. Upload documents, visualize the knowledge graph, and ask questions — all from the browser.

## Architecture

```
make run
├── Docker (Qdrant + NebulaGraph)
├── FastAPI :8000 (REST API + Swagger)
└── Streamlit :8501 (Interactive UI)
       │
       ▼
  ┌─────────┬──────────┬──────────┐
  │ Upload  │  Graph    │  Query   │
  │ Docs    │  Explorer │  & Chat  │
  └────┬────┴────┬──────┴────┬─────┘
       └─────────┼───────────┘
                 ▼
            FastAPI API
                 │
     ┌───────────┼───────────┐
     ▼           ▼           ▼
  Qdrant     NebulaGraph  OpenRouter
  (vectors)  (graph)      (LLM+Emb)
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager

### 1. Clone and configure

```bash
git clone <repo-url>
cd graphrag-poc
cp .env.example .env
# Edit .env and add your OpenRouter API key
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Start everything

```bash
make run
```

This starts Docker, initializes NebulaGraph schema, launches the API server, and opens the Streamlit UI.

- **Streamlit UI**: http://localhost:8501
- **API docs (Swagger)**: http://localhost:8000/docs

### 4. Load sample data

Click **"Seed Sample Data"** on the Upload page, or run:

```bash
make seed
```

## What You Can Do

### Upload Documents (Upload page)

Drag-and-drop PDF, TXT, or Markdown files. The system will:
1. Split documents into chunks
2. Extract entity-relation triplets via LLM
3. Store entities and relationships in NebulaGraph
4. Embed triplets and store in Qdrant

### Explore the Graph (Graph page)

Interactive visualization of the knowledge graph:
- Filter by entity type, relation type, or minimum connections
- Click nodes to inspect entity details and connections
- View 1-hop neighborhoods around any entity
- Switch layouts (force-directed, hierarchical, circular)

### Ask Questions (Query page)

Chat interface with streaming support:
- Toggle streaming to see answers generate token-by-token
- Each answer includes confidence score, sources, and entities found
- Chat history persists within the session

### Manage Documents (Documents page)

List, inspect, and delete ingested documents with one click.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check for all services |
| `POST` | `/api/v1/ingest` | Upload and process a document (PDF/TXT/MD) |
| `POST` | `/api/v1/seed` | Ingest sample data |
| `POST` | `/api/v1/query` | Ask a question (sync) |
| `POST` | `/api/v1/query/stream` | Ask a question (streaming SSE) |
| `GET` | `/api/v1/documents` | List ingested documents |
| `DELETE` | `/api/v1/documents/{filename}` | Delete a document and its data |
| `GET` | `/api/v1/graph/stats` | Knowledge graph statistics |
| `GET` | `/api/v1/graph/entities` | List all entities with types and degrees |
| `GET` | `/api/v1/graph/edges` | List all edges (relationships) |
| `GET` | `/api/v1/graph/subgraph` | N-hop neighborhood of an entity |
| `GET` | `/api/v1/graph/filters` | Available filter values |

### Examples

**Upload a document:**

```bash
curl -X POST http://localhost:8000/api/v1/ingest \
  -F "file=@document.txt"
```

**Ask a question:**

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Who created Python?", "top_k": 5}'
```

**Check graph stats:**

```bash
curl http://localhost:8000/api/v1/graph/stats
```

## How It Works

### Ingestion Pipeline

1. **Load** — PyPDFLoader (PDF), TextLoader (TXT/MD)
2. **Chunk** — RecursiveCharacterTextSplitter (1000 chars, 200 overlap)
3. **Extract** — LLM extracts (subject, predicate, object) triplets from each chunk
4. **Store graph** — Entities and relationships stored in NebulaGraph
5. **Store vectors** — Each triplet embedded and stored in Qdrant with metadata

### Query Pipeline

1. **Embed question** — Convert question to vector
2. **Vector search** — Qdrant finds top-K semantically similar triplets
3. **Graph traversal** — NebulaGraph expands context via bidirectional relationships
4. **Fuse contexts** — Deduplicate and merge vector + graph results
5. **Generate answer** — LLM produces answer using structured context
6. **Confidence score** — 70% vector similarity + 30% coverage factor

## Configuration

All settings are in `.env` (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | — | Your OpenRouter API key |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter API base URL |
| `OPENROUTER_LLM_MODEL` | `openai/gpt-4o-mini` | LLM model for extraction and QA |
| `OPENROUTER_EMBEDDING_MODEL` | `openai/text-embedding-3-small` | Embedding model (1536d) |
| `QDRANT_HOST` | `localhost` | Qdrant host |
| `QDRANT_PORT` | `6333` | Qdrant REST port |
| `NEBULA_HOST` | `localhost` | NebulaGraph host |
| `NEBULA_PORT` | `9669` | NebulaGraph graphd port |
| `NEBULA_SPACE` | `graphrag` | NebulaGraph space name |

## Project Structure

```
graphrag-poc/
├── Makefile                     # run, stop, clean, test, seed, init
├── docker-compose.yml           # Qdrant + NebulaGraph
├── config/nebula/               # NebulaGraph configs
├── app/
│   ├── main.py                  # FastAPI app
│   ├── config.py                # Pydantic settings
│   ├── api/routes/              # Endpoint handlers
│   ├── core/                    # LLM, embeddings, graph, vectorstore
│   ├── pipelines/               # Ingestion + query pipelines
│   ├── models/                  # Pydantic schemas
│   └── prompts/                 # LLM prompts
├── ui/
│   ├── app.py                   # Streamlit entrypoint
│   ├── pages/                   # Upload, Graph, Query, Documents
│   └── components/              # api_client, sidebar, graph_renderer
├── tests/                       # 126 unit + integration tests
├── scripts/
│   ├── init_nebula.py           # Initialize NebulaGraph schema
│   └── seed.py                  # Load sample data
└── docs/
    ├── PRD.md                   # Original product requirements
    └── PRD-STREAMLIT.md         # Streamlit UI requirements
```

## Running Tests

```bash
make test
```

Unit tests run with mocks (no Docker needed). Integration tests require Docker services and an API key.

## Stopping Services

```bash
make stop        # stop Docker
make clean       # stop Docker + remove all data volumes
```