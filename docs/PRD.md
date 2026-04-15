# PRD: GraphRAG Chatbot PoC

## 1. Project Summary

A GraphRAG-powered chatbot that processes documents (PDF, TXT, Markdown), extracts knowledge triplets (entity-relation-entity), builds a knowledge graph, generates embeddings for hybrid retrieval (vector + graph), and answers questions with structured, traceable context.

## 2. Objectives

| # | Objective | Success Criteria |
|---|-----------|-------------------|
| O1 | Ingest documents and extract triplets | Process PDF/TXT/MD and store triplets in NebulaGraph |
| O2 | Generate triplet embeddings | Store vectors in Qdrant with graph metadata |
| O3 | Hybrid retrieval (vector + graph) | Combine similarity search + graph traversal for context |
| O4 | Structured answers via API | FastAPI endpoint returning answers with traceable sources |
| O5 | Reproducible infrastructure | Everything runs with a single `docker-compose up` |

## 3. Tech Stack

| Component | Technology | Role |
|-----------|------------|------|
| Orchestrator | **LangChain** | Ingestion pipelines, chains, agents |
| LLM | **OpenRouter** (GPT-4o / Claude) | Entity/relation extraction, answer generation |
| Embeddings | **OpenRouter** | Triplet and query embeddings |
| Vector DB | **Qdrant** | Semantic search over triplets |
| Graph DB | **NebulaGraph** | Knowledge graph storage and traversal |
| API | **FastAPI** | Chatbot REST interface |
| Infra | **Docker Compose** | Service orchestration |

## 4. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI (REST API)                     │
│                 /ingest  |  /query                        │
└────────┬────────────────┼───────────────────┬───────────┘
         │                │                    │
    ┌────▼─────┐    ┌─────▼──────┐     ┌──────▼──────┐
    │ INGESTION │    │  QUERY     │     │   HEALTH    │
    │ PIPELINE  │    │  PIPELINE  │     │   CHECKS    │
    └────┬─────┘    └─────┬──────┘     └─────────────┘
         │                │
    ┌────▼────────────────▼──────┐
    │      LangChain             │
    │  (chains, parsers, etc.)   │
    └────┬────────────────┬─────┘
         │                │
    ┌────▼─────┐   ┌─────▼──────────┐   ┌────────────┐
    │ Qdrant   │   │ NebulaGraph     │   │ OpenRouter │
    │ (vectors)│   │ (knowledge      │   │ (LLM/Emb) │
    │          │   │  graph)         │   │            │
    └──────────┘   └────────────────┘   └────────────┘
```

## 5. Ingestion Pipeline (Documents → Graph + Vectors)

```
File → Parse (LangChain Loader) → Chunks (TextSplitter)
     → LLM extracts entities/relations → Triplets (S,P,O)
     → Store in NebulaGraph
     → Embed each triplet → Store in Qdrant (with metadata: graph IDs)
```

**Detailed steps:**

1. **Load**: `PyPDFLoader`, `TextLoader`, `UnstructuredMarkdownLoader`
2. **Chunking**: `RecursiveCharacterTextSplitter` (overlap to preserve context)
3. **Extraction**: LLM via OpenRouter extracts entities and relations with a structured prompt
4. **Triplets**: `(Subject, Predicate, Object)` format with entity types
5. **Graph**: Insert vertices and edges into NebulaGraph (space: `graphrag`)
6. **Embeddings**: Embed composite triplet text → Qdrant with payload `{vertex_ids, chunk_id, source}`

## 6. Query Pipeline (Question → Answer)

```
Query → Embed query
      → Qdrant: similarity search → top-K relevant triplets
      → NebulaGraph: graph traversal from found entities
      → Combined context (triplets + graph neighbors)
      → LLM generates answer with structured context
      → Answer + sources
```

**Hybrid strategy:**

- **Vector search**: Finds semantically similar triplets
- **Graph traversal**: Expands context by navigating relationships from found entities (1-2 hops)
- **Fusion**: Combines both contexts, deduplicates, feeds to the LLM

## 7. API Endpoints (FastAPI)

| Method | Route | Description |
|--------|-------|-------------|
| `POST` | `/api/v1/ingest` | Upload document(s) for processing |
| `POST` | `/api/v1/query` | Submit a question, receive an answer |
| `GET` | `/api/v1/documents` | List ingested documents |
| `DELETE` | `/api/v1/documents/{id}` | Delete document and its graph + vector data |
| `GET` | `/api/v1/graph/stats` | Graph statistics (# entities, relations) |
| `GET` | `/health` | Health check for all services |

**Expected Request/Response:**

```json
// POST /api/v1/query
// Request:
{"question": "Who founded X?", "top_k": 5}

// Response:
{
  "answer": "...",
  "sources": [{"chunk_id": "...", "document": "...", "triplets": [...]}],
  "entities_found": [...],
  "confidence": 0.85
}
```

## 8. Data Model

### NebulaGraph Schema (Space: `graphrag`)

```ngql
-- Tag (Vertex types)
CREATE TAG entity (name string, type string, description string);
CREATE TAG chunk (content string, source string, index int);

-- Edge types
CREATE EDGE related_to (relation string, weight double);
CREATE EDGE contains_chunk (position int);
CREATE EDGE same_as (confidence double);
```

### Qdrant Collection: `triplets`

```json
{
  "vectors": {"size": 1536, "distance": "Cosine"},
  "payload_schema": {
    "subject": "keyword",
    "predicate": "keyword",
    "object": "keyword",
    "subject_id": "keyword",
    "object_id": "keyword",
    "chunk_id": "keyword",
    "source_doc": "keyword"
  }
}
```

## 9. Project Structure

```
graphrag-poc/
├── docker-compose.yml
├── .env.example
├── pyproject.toml
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app
│   ├── config.py                # Settings (pydantic)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── ingest.py
│   │   │   ├── query.py
│   │   │   └── documents.py
│   │   └── deps.py              # Dependency injection
│   ├── core/
│   │   ├── __init__.py
│   │   ├── llm.py               # OpenRouter client wrapper
│   │   ├── embeddings.py        # Embedding client wrapper
│   │   ├── graph.py             # NebulaGraph client wrapper
│   │   └── vectorstore.py       # Qdrant client wrapper
│   ├── pipelines/
│   │   ├── __init__.py
│   │   ├── ingestion.py         # Ingestion pipeline (LangChain)
│   │   └── query.py             # Query pipeline (LangChain)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py           # Pydantic request/response models
│   │   └── graph_schema.py      # NebulaGraph schema definitions
│   └── prompts/
│       ├── __init__.py
│       ├── extraction.py        # Entity/relation extraction prompts
│       └── qa.py                # Question-answering prompts
├── tests/
│   ├── __init__.py
│   ├── test_ingest.py
│   └── test_query.py
└── scripts/
    ├── init_nebula.py           # Initialize NebulaGraph schema
    └── seed.py                  # Seed with sample data
```

## 10. Milestones (Development Phases)

### Phase 1 — Infrastructure & Connectivity

- Docker Compose with Qdrant + NebulaGraph + API
- Verified connections to each service from Python
- Working health checks
- `.env` configuration with OpenRouter API key

### Phase 2 — Ingestion Pipeline

- Loaders for PDF/TXT/MD
- Chunking with RecursiveCharacterTextSplitter
- Entity/relation extraction prompt
- Insertion into NebulaGraph
- Embedding generation → Qdrant

### Phase 3 — Query Pipeline

- Query embedding → Qdrant search
- Graph traversal from found entities
- Vector + graph context fusion
- LLM answer generation

### Phase 4 — API & Endpoints

- POST /ingest, POST /query, GET /documents
- Error handling and validation
- Source traceability in responses

### Phase 5 — Polish & Testing

- Unit and integration tests
- API documentation (OpenAPI/Swagger)
- Prompt cleanup and optimization
- README with instructions

## 11. Non-Functional Requirements

| Aspect | Requirement |
|--------|-------------|
| Security | API key in `.env`, never hardcoded. Basic rate limiting |
| Logging | Structured logging with `structlog` |
| Errors | Graceful handling when services are down (NebulaGraph/Qdrant) |
| Scalability | Async design where possible (FastAPI natively) |
| Observability | Pipeline step logging for debugging |