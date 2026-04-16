# GraphRAG PoC

Hybrid RAG system con Google ADK, Qdrant y NebulaGraph. Dos sistemas de memoria agentiva: Soporte Virtual y Account Manager.

## Sistemas

| Sistema | Propósito |
|---------|-----------|
| **A (Soporte)** | Base de conocimiento con filtros por producto/versión, respuesta con fuentes |
| **B (Account Manager)** | Memoria longitudinal: facts, episodios, compromisos, continuidad |

## Arquitectura

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
   (vectors)  (graph)       (LLM+Emb)
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

### 1. Clone y configurar

```bash
git clone https://github.com/Mortiz98/graphrag-poc.git
cd graphrag-poc
cp .env.example .env
# Edit .env: agregar OPENROUTER_API_KEY o GEMINI_API_KEY
```

### 2. Instalar

```bash
uv sync
```

### 3. Iniciar

```bash
make run
```

- **Streamlit UI**: http://localhost:8501
- **API docs**: http://localhost:8000/docs

### 4. Cargar datos de prueba

```bash
make seed
```

## API Endpoints

| Method | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/ingest` | Subir documento (PDF/TXT/MD) |
| `POST` | `/api/v1/seed` | Cargar sample.txt |
| `POST` | `/api/v1/query` | Consulta sync |
| `POST` | `/api/v1/query/stream` | Consulta streaming (SSE) |
| `GET` | `/api/v1/documents` | Listar documentos |
| `DELETE` | `/api/v1/documents/{filename}` | Eliminar documento |
| `GET` | `/api/v1/graph/*` | Endpoints de grafo |
| `GET` | `/api/v1/traces/*` | Retrieval traces |
| `POST` | `/api/v1/agents/support/query` | Agente de soporte (ADK) |
| `POST` | `/api/v1/agents/am/query` | Agente Account Manager (ADK) |

## Fases de Desarrollo

| Fase | Estado | Descripción |
|------|--------|-------------|
| 0 | ✅ | Plataforma base ADK + retrieval + evals |
| 1A | 🔄 | MVP Soporte (grounded responses) |
| 1B | ⏳ | MVP Account Manager (continuity) |
| 2 | ⏳ | Sparse + hybrid + reranking |
| 3A/3B | ⏳ | Grafos de dominio y temporal |
| 4-5 | ⏳ | Experimentos y escalado |

## Cómo Funciona

### Ingestión

1. **Load** — PDF/TXT/MD
2. **Chunk** — RecursiveCharacterTextSplitter (1000 chars, 200 overlap)
3. **Extract** — LLM extrae tripletas (sujeto → predicado → objeto)
4. **Store graph** — Entidades y relaciones en NebulaGraph
5. **Store vectors** — Tripletas embeddas en Qdrant

### Query

1. **Embed question** → vector
2. **Dense search** — Qdrant top-K
3. **Graph expansion** — NebulaGraph expande contexto
4. **Fuse** — Deduplicar resultados
5. **Generate** — LLM produce respuesta

## Configuración (.env)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | — | OpenRouter key |
| `GEMINI_API_KEY` | — | Google Gemini key (opcional) |
| `OPENROUTER_LLM_MODEL` | `openai/gpt-4o-mini` | LLM |
| `OPENROUTER_EMBEDDING_MODEL` | `text-embedding-3-small` | Embeddings (1536d) |
| `QDRANT_HOST` | `localhost` | Qdrant |
| `NEBULA_HOST` | `localhost` | NebulaGraph |
| `NEBULA_SPACE` | `graphrag` | Space name |

## Proyecto

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
├── evals/              # métricas y truth sets
├── ui/                 # Streamlit pages
└── tests/              # 199 tests
```

## Tests

```bash
make test
# o: uv run pytest tests/ -v
```

## Evaluación

```bash
python -c "from evals.runner import run_retrieval_eval; print(run_retrieval_eval('evals/truth_sets/support_qa.jsonl'))"
```