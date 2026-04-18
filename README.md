# GraphRAG PoC

Sistema híbrido de memoria para dos sistemas agentivos — Google ADK + Qdrant + NebulaGraph + Gemini.

## Sistemas

| Sistema | Propósito | Unidad dominante |
|---------|-----------|-----------------|
| **A — Soporte Virtual** | Recuperar y sintetizar conocimiento sobre incidentes, síntomas, causas, resoluciones y políticas | Corpus-centric (caso, ticket, documento) |
| **B — Account Manager** | Sostener continuidad relacional y operativa a lo largo del tiempo, preservando hechos, compromisos y relaciones | Account-centric y temporal (cuenta, stakeholder) |

Ambos comparten la plataforma base pero tienen topologías lógicas distintas.

## Arquitectura

```
┌──────────────────────────────────────────────────────────┐
│  Streamlit :8501                                         │
│  Upload │ Graph │ Query (support/am) │ Documents        │
├──────────────────────────────────────────────────────────┤
│  FastAPI :8000                                           │
│  /ingest  /query  /agents/*  /traces  /artifacts  /graph │
├──────────────────────────────────────────────────────────┤
│  Google ADK                                              │
│  support_agent (3 tools)                                 │
│  account_manager_agent (10 tools: 6 read + 4 write)     │
│  Session ✅  Artifact ✅  Memory ✅                      │
├──────────────────────────────────────────────────────────┤
│  Pipelines                                               │
│  ingestion → consolidation → store dual                  │
│  query → dense → graph → fuse → generate                │
│  memory_writer → record_fact / supersede_fact            │
├──────────────────────────────────────────────────────────┤
│  Core                                                    │
│  genai (Gemini, single stack) │ RetrievalEngine          │
│  AccountStore (estado autoritativo)                      │
│  NebulaGraph pool             │ Qdrant singleton         │
├──────────────┬───────────────────────────────────────────┤
│   Qdrant      │   NebulaGraph                            │
│  triplets     │   entity, issue, stakeholder,            │
│  768d COSINE  │   commitment (tags)                     │
│  is_active    │   has_symptom, caused_by, resolved_by,   │
│  fact_type    │   affects, escalated_to, owns, ...       │
│  memory_type  │   (edges de dominio)                    │
│  10 indexes   │                                         │
└──────────────┴───────────────────────────────────────────┘
```

## Inicio Rápido

### Requisitos

- Docker & Docker Compose
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

### 1. Clonar y configurar

```bash
git clone https://github.com/Mortiz98/graphrag-poc.git
cd graphrag-poc
cp .env.example .env
# Editar .env: agregar GEMINI_API_KEY
```

### 2. Instalar

```bash
uv sync
```

### 3. Iniciar

```bash
make run
```

Esto levanta Docker (Qdrant + NebulaGraph), inicializa el schema, y arranca la API y Streamlit.

- **Streamlit UI**: http://localhost:8501
- **Documentación API**: http://localhost:8000/docs

### 4. Cargar datos

Subí documentos desde la página **Upload** en la UI, o usá el botón "Seed Sample Data", o por CLI:

```bash
make seed
```

### 5. Consultar

- Desde la UI: página **Query** → elegí agente (Support o Account Manager) → preguntá
- Desde API: `curl -X POST http://localhost:8000/api/v1/agents/support/query -d "question=What is Python?"`

## Cómo Funciona

### Ingesta

1. **Load** — PDF, TXT o Markdown
2. **Chunk** — RecursiveCharacterTextSplitter (1000 chars, 200 overlap)
3. **Extract** — Gemini extrae tripletas tipadas:
   - Soporte: `Issue → has_symptom → Symptom`, `Issue → caused_by → RootCause`, `RootCause → resolved_by → Fix`
   - Genérico: `Entity → relation → Entity`
4. **Consolidate** — clasificar memoria (state/episodic/semantic/procedural) → deduplicar (coseno > 0.95) → aplicar supersession
5. **Store dual** — NebulaGraph (vértices + aristas) + Qdrant (embeddings 768d con metadata)

### Consulta directa

1. Embed pregunta → `search_dense(top_k, active_only=True)` en Qdrant
2. IDs de entidades → `expand_from_graph()` en NebulaGraph
3. Fusionar y deduplicar resultados
4. Gemini genera respuesta con contexto

### Consulta por agente (ADK)

1. Runner invoca agente con sesión ADK
2. El agente decide qué tools llamar:
   - **Support**: `search_knowledge_base`, `search_by_metadata`, `traverse_issue_graph`
   - **AM**: tools de lectura + `write_fact`, `update_fact`, `write_commitment`, `write_stakeholder`
3. Las tools delegan a `RetrievalEngine` y `AccountStore`
4. El agente sintetiza la respuesta

### Supersesión

- Cuando un hecho reemplaza otro: el viejo se marca `is_active=False`, `valid_to=now`, `superseded_by=new_id`
- Por defecto, las consultas excluyen hechos inactivos (`active_only=True`)

## Endpoints API

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check (Qdrant + NebulaGraph + Gemini + ADK) |
| `POST` | `/api/v1/ingest` | Subir documento (PDF/TXT/MD) con metadata |
| `POST` | `/api/v1/seed` | Cargar sample.txt |
| `POST` | `/api/v1/query` | Consulta directa (pipeline, `active_only=True`) |
| `POST` | `/api/v1/query/stream` | Consulta streaming (SSE) |
| `GET` | `/api/v1/documents` | Listar documentos |
| `DELETE` | `/api/v1/documents/{filename}` | Eliminar documento |
| `GET` | `/api/v1/graph/*` | Entidades, aristas, subgrafos, filtros |
| `GET` | `/api/v1/traces/*` | Retrieval traces |
| `GET/POST` | `/api/v1/artifacts/*` | System prompts y playbooks |
| `POST` | `/api/v1/agents/support/query` | Agente de soporte (ADK) |
| `POST` | `/api/v1/agents/support/query/stream` | Agente de soporte streaming |
| `POST` | `/api/v1/agents/am/query` | Agente Account Manager (ADK) |
| `POST` | `/api/v1/agents/am/query/stream` | Agente AM streaming |
| `GET` | `/api/v1/agents/am/state/{id}` | Estado de cuenta |

## Configuración (.env)

| Variable | Default | Descripción |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Clave Google Gemini (requerida) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Modelo LLM |
| `GEMINI_EMBEDDING_MODEL` | `gemini-embedding-001` | Modelo embeddings |
| `QDRANT_HOST` | `localhost` | Host Qdrant |
| `QDRANT_PORT` | `6333` | Puerto REST Qdrant |
| `QDRANT_GRPC_PORT` | `6334` | Puerto gRPC Qdrant |
| `NEBULA_HOST` | `localhost` | Host NebulaGraph |
| `NEBULA_PORT` | `9669` | Puerto NebulaGraph |
| `NEBULA_SPACE` | `graphrag` | Nombre del space |

## Fases de Desarrollo

| Fase | Estado | Descripción |
|------|--------|-------------|
| 0 | ✅ Completa | Plataforma base: ADK, retrieval, Qdrant, namespaces, consolidación, evals |
| 1A | 🔄 ~55% | MVP Soporte: ingesta orientada a caso, respuestas grounded, tools enriquecidas |
| 1B | 🔄 ~40% | MVP AM: escritura, AccountStore, grafo en ingesta, prompt domain-specific |
| 2 | ⏳ | Sparse + hybrid retrieval, reranking, query rewriting |
| 3A/3B | ⏳ | Grafos de dominio (soporte) y temporal (AM) |
| 4 | ⏳ | Carriles experimentales: multi-vector, Wholembed, Graphiti POC |
| 5 | ⏳ | Managed, persistencia, seguridad, escalado |

Ver [`docs/PRD.md`](docs/PRD.md) para el plan completo con especificaciones, métricas y deuda técnica.

## Estructura del Proyecto

```
graphrag-poc/
├── Makefile
├── docker-compose.yml
├── app/
│   ├── main.py
│   ├── config.py
│   ├── agents/            # Google ADK agents + tools + prompts
│   ├── api/routes/        # FastAPI endpoints
│   ├── core/              # genai, retrieval, graph, vectorstore, account_store
│   ├── pipelines/         # ingestion, query, consolidation, memory_writer
│   ├── models/            # Pydantic schemas, graph schema
│   └── prompts/           # Extraction (generic + support) and QA prompts
├── evals/                 # Metrics, truth sets, runner
├── ui/                    # Streamlit pages and components
├── test_data/             # Sample data for seeding
├── scripts/               # init_nebula, seed
└── tests/                 # 199 unit tests
```

## Tests

```bash
make test
# o: uv run ruff check app/ tests/ evals/ ui/ && uv run ruff format app/ tests/ evals/ ui/ && uv run pytest tests/ -v
```

199 tests, 2 skipped (requieren Docker). Unit tests con mocks, no necesitan Docker.

## Evaluación

```bash
python -c "from evals.runner import run_retrieval_eval; print(run_retrieval_eval('evals/truth_sets/support_qa.jsonl'))"
```

Métricas disponibles: relevance@k, MRR, nDCG, grounding rate, recall@k.
