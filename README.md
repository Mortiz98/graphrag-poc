# GraphRAG PoC

Sistema hibrido RAG con Google ADK, Qdrant y NebulaGraph. Dos sistemas de memoria agentiva: Soporte Virtual y Account Manager.

## Sistemas

| Sistema | Proposito |
|---------|-----------|
| **A (Soporte)** | Base de conocimiento con filtros por producto/version, respuestas fundamentadas |
| **B (Account Manager)** | Memoria longitudinal: hechos, episodios, compromisos, continuidad |

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
   (vectors)  (graph)     (LLM+Emb)
      │
      ▼
   Google ADK
   (agents)
```

## Inicio Rapido

### Requisitos

- Docker & Docker Compose
- Python 3.10+
- [uv](https://docs.astral.sh/uv/)

### 1. Clonar y configurar

```bash
git clone https://github.com/Mortiz98/graphrag-poc.git
cd graphrag-poc
cp .env.example .env
# Editar .env: agregar OPENROUTER_API_KEY o GEMINI_API_KEY
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
- **Documentacion API**: http://localhost:8000/docs

### 4. Cargar datos de prueba

```bash
make seed
```

## Endpoints API

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/ingest` | Subir documento (PDF/TXT/MD) |
| `POST` | `/api/v1/seed` | Cargar sample.txt |
| `POST` | `/api/v1/query` | Consulta sincronica |
| `POST` | `/api/v1/query/stream` | Consulta streaming (SSE) |
| `GET` | `/api/v1/documents` | Listar documentos |
| `DELETE` | `/api/v1/documents/{filename}` | Eliminar documento |
| `GET` | `/api/v1/graph/*` | Endpoints de grafo |
| `GET` | `/api/v1/traces/*` | Retrieval traces |
| `POST` | `/api/v1/agents/support/query` | Agente de soporte (ADK) |
| `POST` | `/api/v1/agents/am/query` | Agente Account Manager (ADK) |

## Fases de Desarrollo

| Fase | Estado | Descripcion |
|------|--------|-------------|
| 0 | ✅ | Plataforma base, ADK, retrieval, evals |
| 1A | 🔄 | MVP Soporte (respuestas fundamentadas) |
| 1B | ⏳ | MVP Account Manager (continuidad) |
| 2 | ⏳ | Sparse + hybrid + reranking |
| 3A/3B | ⏳ | Grafos de dominio y temporal |
| 4-5 | ⏳ | Experimentos y escalado |

## Como Funciona

### Ingestion

1. **Load** — PDF/TXT/MD
2. **Chunk** — RecursiveCharacterTextSplitter (1000 chars, 200 overlap)
3. **Extract** — LLM extrae tripletas (sujeto → predicado → objeto)
4. **Store graph** — Entidades y relaciones en NebulaGraph
5. **Store vectors** — Tripletas embeddadas en Qdrant

### Query

1. **Embed question** → vector
2. **Dense search** — Qdrant top-K
3. **Graph expansion** — NebulaGraph expande contexto
4. **Fuse** — Deduplicar resultados
5. **Generate** — LLM produce respuesta

## Configuracion (.env)

| Variable | Default | Descripcion |
|----------|---------|-------------|
| `OPENROUTER_API_KEY` | — | Clave OpenRouter |
| `GEMINI_API_KEY` | — | Clave Google Gemini (opcional) |
| `OPENROUTER_LLM_MODEL` | `openai/gpt-4o-mini` | LLM |
| `OPENROUTER_EMBEDDING_MODEL` | `text-embedding-3-small` | Embeddings (1536d) |
| `QDRANT_HOST` | `localhost` | Qdrant |
| `NEBULA_HOST` | `localhost` | NebulaGraph |
| `NEBULA_SPACE` | `graphrag` | Nombre del space |

## Estructura del Proyecto

```
graphrag-poc/
├── Makefile
├── docker-compose.yml
├── app/
│   ├── main.py
│   ├── config.py
│   ├── agents/          # Agentes Google ADK
│   ├── api/routes/
│   ├── core/           # LLM, embeddings, graph, vectorstore, retrieval
│   ├── pipelines/       # ingestion, query, consolidation
│   └── models/
├── evals/              # metricas y truth sets
├── ui/                 # Paginas Streamlit
└── tests/              # 199 tests
```

## Tests

```bash
make test
# o: uv run pytest tests/ -v
```

## Evaluacion

```bash
python -c "from evals.runner import run_retrieval_eval; print(run_retrieval_eval('evals/truth_sets/support_qa.jsonl'))"
```