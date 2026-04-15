# Architecture Documentation

## System Overview

GraphRAG PoC is a hybrid RAG (Retrieval-Augmented Generation) system that combines:
- **Vector search** (Qdrant) for semantic similarity
- **Graph traversal** (NebulaGraph) for relationship expansion
- **LLM generation** (OpenRouter) for answer synthesis

The system exposes two interfaces:
- **FastAPI** REST API (`:8000`) for programmatic access
- **Streamlit** UI (`:8501`) for interactive exploration

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                           Streamlit UI (:8501)                       │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────┐              │
│  │Dashboard│  │ Upload  │  │  Graph  │  │    Query    │              │
│  └────┬────┘  └────┬────┘  └────┬────┘  └──────┬──────┘              │
│       │           │           │              │                      │
│       └───────────┴───────────┴──────────────┘                      │
│                         │                                            │
│                         ▼                                            │
│              ┌──────────────────────┐                               │
│              │   httpx Client      │                               │
│              │   (api_client.py)   │                               │
│              └──────────┬───────────┘                               │
└─────────────────────────┼───────────────────────────────────────────┘
                          │ HTTP
                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        FastAPI (:8000)                               │
│  ┌──────────┬───────────┬─────────┬──────────┬───────────┐          │
│  │ /health  │ /ingest  │ /query  │/documents│  /graph   │          │
│  │  /seed   │/query/stream                                  │          │
│  └──────────┴───────────┴─────────┴──────────┴───────────┘          │
│                         │                                            │
│       ┌─────────────────┼─────────────────┐                          │
│       │                 │                 │                          │
│       ▼                 ▼                 ▼                          │
│  ┌──────────┐   ┌──────────────┐   ┌─────────────┐                   │
│  │ Health   │   │  Ingestion   │   │   Query     │                   │
│  │  Check   │   │   Pipeline   │   │   Pipeline  │                   │
│  └──────────┘   └──────┬───────┘   └──────┬──────┘                   │
│                        │                  │                          │
│                        └────────┬─────────┘                          │
│                                 ▼                                    │
│                    ┌─────────────────────┐                           │
│                    │    LangChain LLM    │                           │
│                    │  (OpenRouter/GPT)   │                           │
│                    └──────────┬──────────┘                           │
└────────────────────────────────┼─────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         ▼                       ▼                       ▼
   ┌──────────┐          ┌──────────────┐        ┌────────────┐
   │  Qdrant  │          │ NebulaGraph  │        │ OpenRouter │
   │(vectors) │          │   (graph)    │        │ (LLM+Emb)  │
   └──────────┘          └──────────────┘        └────────────┘
```

## Data Flow

### Ingestion Flow

```
File Upload
    │
    ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Loader    │───▶│  Chunker   │───▶│  Extractor │
│ (PDF/TXT/MD)│    │ (Recursive │    │  (LLM)     │
└─────────────┘    │ TextSplit) │    └──────┬──────┘
                  └─────────────┘           │
                                           ▼
                              ┌─────────────────────┐
                              │   Triplets List     │
                              │ (S, P, O, types)    │
                              └──────────┬──────────┘
                                         │
                    ┌────────────────────┴────────────────────┐
                    ▼                                         ▼
            ┌──────────────┐                         ┌──────────────┐
            │  NebulaGraph │                         │   Qdrant     │
            │  Vertices    │                         │   Vectors    │
            │  Edges       │                         │   +Payload   │
            └──────────────┘                         └──────────────┘
```

### Query Flow

```
User Question
       │
       ▼
┌─────────────────┐
│ Embed Question │◀──── OpenRouter
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│  Vector Search  │────▶│ Graph Traversal │
│   (Qdrant)     │     │  (NebulaGraph)  │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
           ┌─────────────────┐
           │ Context Fusion │
           │  (Dedupe)      │
           └────────┬────────┘
                    │
                    ▼
           ┌─────────────────┐
           │  LLM Generate  │
           │   Answer       │
           └────────┬────────┘
                    │
                    ▼
           Response + Confidence + Sources
```

## Database Schemas

### NebulaGraph (Space: `graphrag`)

```ngql
-- Tags
CREATE TAG entity (name string, type string, description string);

-- Edges  
CREATE EDGE related_to (relation string, weight double);
```

### Qdrant (Collection: `triplets`)

```json
{
  "vectors": {
    "size": 1536,
    "distance": "Cosine"
  },
  "payload": {
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

## API Routes

### Ingest Routes

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/ingest` | Upload document |
| `POST` | `/api/v1/seed` | Load sample data |

### Query Routes

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/query` | Sync query |
| `POST` | `/api/v1/query/stream` | Streaming query (SSE) |

### Document Routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/documents` | List all documents |
| `DELETE` | `/api/v1/documents/{filename}` | Delete document |

### Graph Routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/graph/stats` | Graph statistics |
| `GET` | `/api/v1/graph/entities` | All entities with degrees |
| `GET` | `/api/v1/graph/edges` | All edges |
| `GET` | `/api/v1/graph/subgraph` | N-hop neighborhood |
| `GET` | `/api/v1/graph/filters` | Available filter values |

### Health Routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/health` | System health check |

## Key Implementation Details

### Connection Pooling

- **NebulaGraph**: Singleton `ConnectionPool` in `app/core/graph.py` with thread-safe initialization
- **Qdrant**: Created per-request via `get_qdrant_client()`

### Payload Indexes

Qdrant automatically creates indexes on:
- `source_doc`
- `chunk_id`
- `subject_id`
- `object_id`

This enables efficient filtered queries for document management.

### Confidence Calculation

```
confidence = (avg_vector_similarity * 0.7) + (coverage_factor * 0.3)
```

Where:
- `avg_vector_similarity`: Average similarity score from Qdrant
- `coverage_factor`: min(fused_triplets_count / 3, 1.0)

### Streaming Response

The `/query/stream` endpoint uses Server-Sent Events (SSE):
- LLM configured with `streaming=True`
- Response streamed token-by-token via `yield`
- Frontend renders with cursor `▌` placeholder

## Streamlit Pages

| Page | File | Features |
|------|------|----------|
| Dashboard | `ui/app.py` | Stats, recent activity |
| Upload | `ui/pages/1_Upload.py` | File uploader, seed button |
| Graph | `ui/pages/2_Graph.py` | Interactive cytoscape visualization |
| Query | `ui/pages/3_Query.py` | Chat interface, streaming toggle |
| Documents | `ui/pages/4_Documents.py` | List, delete, view in graph |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | — | Required for LLM |
| `OPENROUTER_LLM_MODEL` | `openai/gpt-4o-mini` | LLM model |
| `OPENROUTER_EMBEDDING_MODEL` | `openai/text-embedding-3-small` | Embeddings |
| `QDRANT_HOST` | `localhost` | Qdrant host |
| `QDRANT_PORT` | `6333` | Qdrant port |
| `NEBULA_HOST` | `localhost` | NebulaGraph host |
| `NEBULA_PORT` | `9669` | NebulaGraph port |
| `NEBULA_SPACE` | `graphrag` | Graph space name |