# GraphRAG PoC

Sistema híbrido de memoria para dos sistemas agenciales — Google ADK + Qdrant + NebulaGraph + Gemini.

## Sistemas

| Sistema | Propósito | Unidad dominante |
|---------|-----------|-----------------|
| **A — Soporte Virtual** | Recuperar y sintetizar conocimiento sobre incidentes, síntomas, causas, resoluciones y políticas | Corpus-céntrico (caso, ticket, documento) |
| **B — Account Manager** | Sostener continuidad relacional y operativa a lo largo del tiempo, preservando hechos, compromisos y relaciones | Cuenta-céntrico y temporal (cuenta, stakeholder) |

Ambos comparten infraestructura (colección Qdrant `triplets`, space NebulaGraph `graphrag`) pero se aíslan lógicamente vía `system` + `account_id` + `tenant_id` en el payload.

## Arquitectura

Ver [`docs/architecture.md`](docs/architecture.md) para la especificación completa.

```
┌─────────────────────────────────────────────────────────────┐
│  Presentación                                                │
│  Streamlit :8501          FastAPI :8000                      │
│  Upload│Graph│Query│Docs  /ingest /query /agents/* /traces   │
├─────────────────────────────────────────────────────────────┤
│  Runtime de agentes (Google ADK)                             │
│  support_agent (6 tools, solo lectura)                       │
│  account_manager_agent (10 tools: 6 lectura + 4 escritura)  │
│  InMemorySessionService │ InMemoryArtifactService            │
├─────────────────────────────────────────────────────────────┤
│  Pipelines                                                   │
│  ingestion → consolidation (dedup+supersede) → store dual    │
│  query → dense → graph → fuse → generate                    │
│  memory_writer → record_fact / supersede_fact (solo Qdrant) │
├─────────────────────────────────────────────────────────────┤
│  Core                                                        │
│  genai (Gemini singleton) │ RetrievalEngine (+ traces)       │
│  AccountStore (estado autoritativo)                          │
│  NebulaGraph pool          │ Qdrant singleton (14 indexes)   │
├──────────────────┬──────────────────────────────────────────┤
│  Qdrant          │  NebulaGraph                             │
│  triplets        │  4 tags: entity, issue, stakeholder,     │
│  768d COSINE     │    commitment                            │
│  14 indexes      │  17 edges: has_symptom, caused_by,       │
│                  │    resolved_by, affects, escalated_to,    │
│                  │    governed_by, reported_by, owns,        │
│                  │    responsible_for, affects_version,      │
│                  │    documented_in, depends_on, is_a,       │
│                  │    has_component, produces_error,         │
│                  │    related_to (fallback)                  │
└──────────────────┴──────────────────────────────────────────┘
```

### Agentes y tools

**Soporte (6 tools, solo lectura):**

| Tool | Mecanismo | Cuándo |
|------|-----------|--------|
| `search_knowledge_base` | `search_dense` + scope | Consulta general |
| `search_by_metadata` | `search_dense` + filtros | Usuario especifica product/version/severity |
| `search_by_product` | `search_by_filter` (sin embedding) | Búsqueda por producto |
| `get_resolution_history` | dense → graph (`resolved_by`, `caused_by`) | "¿Cómo resolver X?" |
| `escalation_path` | dense → graph (`escalated_to`, `governed_by`) | "¿A quién escalar?" |
| `traverse_issue_graph` | `expand_from_graph` (todos los edges) | Exploración libre |

**AM (10 tools: 6 lectura + 4 escritura):**

| Tool | Tipo | Mecanismo |
|------|------|-----------|
| `search_knowledge_base` | Lectura | `search_dense` con `system=am` |
| `search_by_metadata` | Lectura | `search_dense` + filtros |
| `search_episodes` | Lectura | `search_dense` con `account_id` |
| `get_account_state` | Lectura | `AccountStore.load_account_state()` |
| `get_commitments` | Lectura | `search_by_filter(fact_type=commitment)` |
| `get_stakeholder_map` | Lectura | `search_by_filter(fact_type=stakeholder)` |
| `write_fact` | Escritura | `memory_writer.record_fact()` |
| `update_fact` | Escritura | `memory_writer.supersede_fact()` |
| `write_commitment` | Escritura | `record_fact(fact_type=commitment)` |
| `write_stakeholder` | Escritura | `record_fact(fact_type=stakeholder)` |

### Formato de respuesta grounded (Soporte)

El prompt obliga al agente a responder con:

```
## Resumen
<1-2 oraciones>

## Pasos sugeridos
1. <paso concreto>

## Evidencia
- <hecho> [fuente: sample.txt]
- <hecho> [fuente: grafo]

## Incertidumbre
<lo no respaldado por evidencia, o "Ninguna">
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

Levanta Docker (Qdrant + NebulaGraph), inicializa schema, arranca API y Streamlit.

- **Streamlit UI**: http://localhost:8501
- **Documentación API**: http://localhost:8000/docs

### 4. Cargar datos

Desde la página **Upload** en la UI, con el botón "Seed Sample Data", o por CLI:

```bash
make seed
```

### 5. Consultar

- **UI**: página **Query** → elegir agente (Support o AM) → preguntar
- **API**: `curl -X POST http://localhost:8000/api/v1/agents/support/query -d "question=¿Cómo resuelvo el timeout de Qdrant?"`

## Pipeline de Ingesta

```
Documento ──load──▶ Chunks ──extract──▶ Tripletas ──consolidate──▶ Store (dual)
```

1. **Load** — PDF, TXT o Markdown
2. **Chunk** — `RecursiveCharacterTextSplitter` (1000 chars, 200 overlap), cada chunk con `chunk_id` + `chunk_index`
3. **Extract** — Gemini extrae tripletas tipadas con routing de dominio:
   - Soporte: tipos Issue/Symptom/RootCause/Fix/Policy/Team/ErrorCode
   - Vértice `Issue` → tag `issue` (severity, product, version), otros → tag `entity`
   - Aristas de dominio → edge correspondiente, desconocidas → `related_to` fallback
4. **Consolidate** — clasificar memoria → deduplicar (coseno > 0.95) → aplicar supersesión
5. **Store dual** — NebulaGraph (vértices + aristas con fallback) + Qdrant (embeddings 768d + payload con metadata)

### Metadata de ingesta

| Campo | Origen | Efecto |
|-------|--------|--------|
| `system` | UI / API | Namespace: `"support"` o `"am"` |
| `tenant_id` | UI / API | Scope por tenant |
| `account_id` | UI / API (solo AM) | Scope por cuenta |
| `product`, `version`, `severity`, `channel` | UI Case Metadata / API | Filtros estructurales (14 payload indexes) |

## Supersesión

- Cuando un hecho reemplaza otro: el viejo se marca `is_active=False`, `valid_to=now`, `superseded_by=new_id`
- Por defecto, las consultas excluyen hechos inactivos (`active_only=True`)
- `memory_writer.supersede_fact()` crea nuevo hecho + actualiza payload del viejo en Qdrant

## Observabilidad

Cada retrieval tool loguea un trace con fase `tool:<nombre>`. Cada interacción de agente loguea un trace global con fase `agent:<nombre>`, incluyendo tools invocadas, duración y session_id. Persistidos como JSONL en `traces/`.

## Endpoints API

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check (Qdrant + NebulaGraph + Gemini + ADK) |
| `POST` | `/api/v1/ingest` | Subir documento con metadata |
| `POST` | `/api/v1/seed` | Cargar sample.txt |
| `POST` | `/api/v1/query` | Consulta directa (pipeline denso+grafo) |
| `POST` | `/api/v1/query/stream` | Consulta streaming (SSE) |
| `GET` | `/api/v1/documents` | Listar documentos |
| `DELETE` | `/api/v1/documents/{filename}` | Eliminar documento |
| `GET` | `/api/v1/graph/*` | Entidades, aristas, subgrafos, filtros |
| `GET` | `/api/v1/traces/*` | Traces de retrieval |
| `GET/POST` | `/api/v1/artifacts/*` | Prompts y playbooks |
| `POST` | `/api/v1/agents/support/query` | Agente de soporte (ADK) |
| `POST` | `/api/v1/agents/support/query/stream` | Soporte streaming |
| `POST` | `/api/v1/agents/am/query` | Agente AM (ADK), requiere `account_id` |
| `POST` | `/api/v1/agents/am/query/stream` | AM streaming |
| `GET` | `/api/v1/agents/am/state/{account_id}` | Snapshot de estado de cuenta |

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
| 1A | ✅ Completa | MVP Soporte: grafo de dominio, respuesta grounded, 6 tools, traces, truth set 25 preguntas, UI metadata |
| 1B | 🔄 ~40% | MVP AM: escritura, AccountStore, prompt domain-specific, eval runner, artifact tools |
| 2 | ⏳ | Sparse + hybrid retrieval, reranking, query rewriting |
| 3A/3B | ⏳ | Grafos de dominio (soporte) y temporal (AM) |
| 4 | ⏳ | Carriles experimentales: multi-vector, Wholembed, Graphiti POC |
| 5 | ⏳ | Managed, persistencia, seguridad, escalado |

Ver [`docs/PRD.md`](docs/PRD.md) para el plan completo. Ver [`docs/architecture.md`](docs/architecture.md) para la arquitectura detallada.

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
└── tests/                 # 228 unit tests
```

## Tests

```bash
make test
# o: uv run ruff check app/ tests/ evals/ ui/ && uv run ruff format app/ tests/ evals/ ui/ && uv run pytest tests/ -v
```

228 tests, 2 skipped (requieren Docker). Unit tests con mocks, no necesitan Docker.

## Evaluación

```bash
# Poblar relevant_chunks post-ingesta (requiere Docker + datos ingeridos)
PYTHONPATH=. uv run python evals/populate_chunks.py

# Correr evaluación
PYTHONPATH=. uv run python -c "from evals.runner import run_retrieval_eval; print(run_retrieval_eval('evals/truth_sets/support_qa.jsonl'))"
```

Métricas disponibles: relevance@k, MRR, nDCG, grounding rate, recall@k.

**Resultados actuales (25 preguntas, español, sample.txt):** relevance@5=1.0, MRR=1.0, recall@5=0.73.
