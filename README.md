# GraphRAG PoC

Knowledge graph + vector search hybrid RAG system. Processes documents (PDF, TXT, Markdown), extracts entity-relation triplets, stores them in a graph database and vector store, and answers questions using both semantic search and graph traversal.

## Architecture

```
                     FastAPI (REST API)
                   /ingest  |  /query
                          │
              ┌───────────┼───────────┐
              │           │           │
         Ingestion    Query Pipeline  Health
         Pipeline                    Checks
              │           │
              └─────┬─────┘
                    │
              LangChain + LLM
              /           \
         ┌────┘             └────┐
    ┌─────┐                    ┌─────┐
    │Qdrant│                    │Nebula│
    │(vecs)│                    │Graph │
    └─────┘                    └─────┘
         │                        │
         └──────── OpenRouter ────┘
              (LLM + Embeddings)
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

### 2. Start services

```bash
docker compose up -d
```

Wait for all containers to be healthy (`docker compose ps`).

### 3. Install dependencies

```bash
uv sync
```

### 4. Initialize NebulaGraph schema

```bash
uv run python -c "from scripts.init_nebula import init_schema; init_schema()"
```

### 5. Start the API

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Or use the script:

```bash
uv run python -m app.main
```

### 6. Open Swagger UI

Navigate to [http://localhost:8000/docs](http://localhost:8000/docs)

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check for all services |
| `POST` | `/api/v1/ingest` | Upload and process a document (PDF/TXT/MD) |
| `POST` | `/api/v1/query` | Ask a question, get an answer with sources |
| `GET` | `/api/v1/documents` | List ingested documents |
| `DELETE` | `/api/v1/documents/{filename}` | Delete a document and its data |
| `GET` | `/api/v1/graph/stats` | Knowledge graph statistics |

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

## Configuration

All settings are in `.env` (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | — | Your OpenRouter API key |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | OpenRouter API base URL |
| `OPENROUTER_LLM_MODEL` | `openai/gpt-4o` | LLM model for extraction and QA |
| `OPENROUTER_EMBEDDING_MODEL` | `openai/text-embedding-3-small` | Embedding model (1536d) |
| `QDRANT_HOST` | `localhost` | Qdrant host |
| `QDRANT_PORT` | `6333` | Qdrant REST port |
| `NEBULA_HOST` | `localhost` | NebulaGraph host |
| `NEBULA_PORT` | `9669` | NebulaGraph graphd port |
| `NEBULA_SPACE` | `graphrag` | NebulaGraph space name |

## Project Structure

```
graphrag-poc/
├── docker-compose.yml          # Qdrant + NebulaGraph
├── config/nebula/              # NebulaGraph configs
├── app/
│   ├── main.py                 # FastAPI app
│   ├── config.py               # Pydantic settings
│   ├── api/
│   │   ├── exceptions.py       # Custom HTTP exceptions
│   │   └── routes/             # Endpoint handlers
│   ├── core/                   # Service wrappers (Qdrant, Nebula, LLM, embeddings)
│   ├── pipelines/
│   │   ├── ingestion.py        # Full ingestion pipeline
│   │   ├── query.py             # Full query pipeline
│   │   └── loaders.py           # Document loaders
│   ├── models/
│   │   ├── schemas.py          # Pydantic request/response models
│   │   └── graph_schema.py     # NebulaGraph schema constants
│   └── prompts/
│       ├── extraction.py        # Entity/relation extraction prompt
│       └── qa.py                # Question answering prompt
├── tests/                      # Unit + integration tests
├── scripts/
│   └── init_nebula.py          # Initialize NebulaGraph schema
└── docs/
    └── PRD.md                  # Product requirements document
```

## Running Tests

```bash
uv run pytest tests/ -v
```

## Stopping Services

```bash
docker compose down
```

To remove all data (volumes):

```bash
docker compose down -v
```