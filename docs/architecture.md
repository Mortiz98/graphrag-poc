# GraphRAG — Arquitectura del Sistema

## 1. Visión general

GraphRAG es una plataforma de memoria dual-agent construida sobre Qdrant (retrieval denso) y NebulaGraph (travesía de grafo), orquestada por agentes Google ADK. Dos sistemas lógicos comparten infraestructura pero difieren en topología y comportamiento:

| | Soporte (A) | Account Manager (B) |
|---|---|---|
| **Modo** | Corpus-céntrico, solo lectura | Cuenta-céntrico, lectura-escritura |
| **Scope** | `system=support` | `system=am`, scope por `account_id` |
| **Agente** | `support_agent` (6 tools) | `account_manager_agent` (10 tools) |
| **Formato respuesta** | Resumen → Pasos → Evidencia → Incertidumbre | Account Overview → Facts → Commitments → Stakeholders → Recommendation |
| **Escrituras** | Ninguna | `write_fact`, `update_fact`, `write_commitment`, `write_stakeholder` |
| **Endpoint** | `/agents/support/query` | `/agents/am/query` |

El aislamiento de namespace es lógico vía campos de payload `system` + `account_id` + `tenant_id`. Ambos comparten colección Qdrant `triplets` y space NebulaGraph `graphrag`.

---

## 2. Topología por capas

```
┌─────────────────────────────────────────────────────────────┐
│  Presentación                                                │
│  Streamlit :8501          FastAPI :8000                      │
│  Upload│Graph│Query│Docs  /ingest /query /agents/* /traces   │
├─────────────────────────────────────────────────────────────┤
│  Runtime de agentes (Google ADK)                             │
│  support_agent ──────── account_manager_agent                │
│  InMemorySessionService │ InMemoryArtifactService            │
│  InMemoryMemoryService                                       │
├─────────────────────────────────────────────────────────────┤
│  Pipelines                                                   │
│  ingestion ── consolidation ── memory_writer                 │
│  query (dense → graph → fuse → generate)                    │
├─────────────────────────────────────────────────────────────┤
│  Core                                                        │
│  genai.py      retrieval.py     graph.py       vectorstore.py│
│  (LLM+emb      (RetrievalEngine  (NebulaGraph   (Qdrant      │
│   singleton)    + traces)         pool+ctx)      singleton)   │
│                                          account_store.py     │
├─────────────────────────────────────────────────────────────┤
│  Stores                                                      │
│  Qdrant: triplets (768d COSINE, 14 indexes)                  │
│  NebulaGraph: graphrag (4 tags, 17 edges)                    │
└─────────────────────────────────────────────────────────────┘
```

### Singletons del Core

Todos los clientes con estado son singletons thread-safe con inicialización lazy:

| Módulo | Acceso | Notas |
|---|---|---|
| `genai.py` | `get_genai_client()` | `genai.Client` único, `generate()` / `generate_stream()` / `embed_documents()` / `embed_query()` |
| `vectorstore.py` | `get_qdrant_client()` | Cliente gRPC Qdrant, `reset_qdrant_client()` para tests |
| `graph.py` | `get_nebula_session()` | Context manager desde pool de conexiones (10 sesiones) |
| `retrieval.py` | `get_retrieval_engine()` | Instancia `RetrievalEngine` con init lazy de Qdrant |

---

## 3. Pipeline de ingesta

```
Documento ──load──▶ Chunks ──extract──▶ Tripletas ──consolidate──▶ Store (dual)
```

### 3.1 Load → Chunk

`load_document()` → `split_documents(chunk_size=1000, overlap=200)`. Cada chunk recibe `chunk_id` (UUID) y `chunk_index`.

### 3.2 Extract

Por cada chunk, Gemini recibe texto + prompt de extracción → retorna JSON array de tripletas tipadas:

```json
{"subject": "QDRANT_CONNECTION_TIMEOUT", "subject_type": "Issue",
 "predicate": "has_symptom", "object": "timeouts en consultas", "object_type": "Symptom"}
```

Existen dos prompts: genérico (`EXTRACTION_SYSTEM_PROMPT`) y específico de soporte (`SUPPORT_EXTRACTION_SYSTEM_PROMPT` con tipos Issue/Symptom/RootCause/Fix/Policy/Team/ErrorCode). Se selecciona por parámetro `system`.

### 3.3 Consolidate

`run_consolidation_pipeline()` aplica tres transformaciones:

1. **Clasificar**: `fact_type` + `system` → `memory_type` (state/episodic/semantic/procedural)
2. **Dedup**: similitud coseno > 0.95 contra tripletas existentes → descartar duplicados (`skip_dedup=False` por defecto)
3. **Supersede**: si el campo `supersedes` está seteado, marcar hecho viejo como `is_active=False`, setear `valid_to` + `superseded_by`

Los resultados SÍ se aplican — las keys sobrevivientes filtran las tripletas originales antes del store.

### 3.4 Store dual

**NebulaGraph** (`store_in_graph`):
- Inserción de vértice enruta vía `ENTITY_TYPE_TO_TAG`: `Issue` → tag `issue`, resto → tag `entity`
- Inserción de arista enruta vía `PREDICATE_TO_EDGE`: predicados conocidos → edge de dominio, desconocido → `related_to`
- Fallback automático: si INSERT con tag/edge de dominio falla, reintentar con `entity`/`related_to`
- IDs de vértice: `_sanitize_vertex_id()` (alfanumérico + underscore + sufijo MD5 hash, máx 256 chars)

**Qdrant** (`store_in_vectorstore`):
- Texto = `"{subject} {predicate} {object}"` → embebido en batches de 20 → upsert como `PointStruct`
- Payload lleva todos los campos de la tripleta + metadata + provenance + flags de estado

### 3.5 Metadata de ingesta

| Campo | Origen | Efecto |
|---|---|---|
| `system` | UI selector / API param | Namespace: `"support"` o `"am"` |
| `tenant_id` | UI / API | Scope por tenant |
| `account_id` | UI / API (solo AM) | Scope por cuenta |
| `product`, `version`, `severity`, `channel` | UI Case Metadata / API | Filtros estructurales (14 payload indexes) |

---

## 4. Paths de consulta

Existen dos paths de consulta distintos: pipeline directo y orquestado por agente.

### 4.1 Pipeline directo (`/api/v1/query`)

Pipeline fijo sin autonomía del agente:

```
Pregunta
  │
  ├─ 1. Retrieval denso: embed_query → search_dense(top_k, scope, filters, active_only=True)
  │
  ├─ 2. Expansión de grafo: extraer entity_ids de (1) → expand_from_graph(entity_ids, hops=1)
  │
  ├─ 3. Fusión: dedup por clave subject|predicate|object, denso primero luego grafo
  │
  └─ 4. Generación: Gemini con QA prompt + contexto fusionado → respuesta
```

Confianza = `avg_similarity * 0.7 + coverage_factor * 0.3` donde coverage = `min(fused_count / 3.0, 1.0)`.

### 4.2 Orquestado por agente (`/api/v1/agents/{support|am}/query`)

ADK Runner crea/restaura sesión → pasa pregunta al `LlmAgent` → agente decide qué tools llamar → puede encadenar múltiples llamadas → sintetiza respuesta final.

**Catálogo de tools del agente de soporte (6):**

| Tool | Estrategia de retrieval | Cuándo |
|---|---|---|
| `search_knowledge_base` | `search_dense` + scope | Consulta general, primer paso |
| `search_by_metadata` | `search_dense` + filtros metadata | Usuario especifica product/version/severity |
| `search_by_product` | `search_by_filter` (sin embedding) | Búsqueda por producto |
| `get_resolution_history` | `search_dense` → `expand_from_graph(relation_types=["resolved_by","caused_by"])` | "¿Cómo resolver X?" |
| `escalation_path` | `search_dense` → `expand_from_graph(relation_types=["escalated_to","governed_by"])` | "¿A quién escalar?" |
| `traverse_issue_graph` | `expand_from_graph` (todos los edges) | Exploración libre del grafo |

**Catálogo de tools del agente AM (10):**

| Tool | Tipo | Mecanismo |
|---|---|---|
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

Las tools compuestas (`get_resolution_history`, `escalation_path`) producen dos entradas de trace: una para dense search, otra para expansión de grafo.

---

## 5. API de RetrievalEngine

| Método | Backend | Estado |
|---|---|---|
| `search_dense(query, top_k, filters, scope, active_only)` | Qdrant `query_points()` | Producción |
| `search_sparse(query, top_k, scope, filters, active_only)` | — | Stub (delega a dense) |
| `search_hybrid(query, top_k, scope, filters, active_only)` | — | Stub (delega a dense) |
| `search_by_filter(top_k, filters, scope, active_only)` | Qdrant `scroll()` | Producción |
| `rerank(candidates, query)` | — | Passthrough |
| `expand_from_graph(entity_ids, hops, relation_types)` | NebulaGraph `GO FROM ... OVER` | Producción |
| `fuse_results(dense, graph)` | Dedup en memoria | Producción |
| `get_supporting_chunks(ids)` | Qdrant `scroll()` por chunk_id | Producción |
| `log_trace(...)` | Archivo JSONL | Producción |

`active_only=True` es el default en todos los métodos — filtra `is_active=True` para excluir hechos supersedados.

---

## 6. Schema del grafo

### Tags

| Tag | Propiedades | Routing |
|---|---|---|
| `entity` | name, type, description | Default; fallback cuando falla INSERT de dominio |
| `issue` | name, severity, status, product, version, channel, description | `subject_type="Issue"` |
| `stakeholder` | name, role, account_id, email, description | `subject_type` ∈ Person/Stakeholder |
| `commitment` | name, account_id, due_date, status, description | `subject_type="Commitment"` |

### Edges (16 de dominio + 1 fallback)

| Edge | Propiedades | Dominio |
|---|---|---|
| `has_symptom` | context | Issue → Symptom |
| `caused_by` | confidence | Issue → RootCause |
| `resolved_by` | step_order, outcome | Issue → Fix |
| `affects` | scope | Issue/Entity → Scope |
| `escalated_to` | reason, priority | Issue → Team |
| `governed_by` | policy_type | Issue → Policy |
| `reported_by` | channel, reported_at | Issue → Channel |
| `owns` | role, since | Stakeholder → Commitment |
| `responsible_for` | role, since | Stakeholder → Issue |
| `affects_version` | version | Issue → Version |
| `documented_in` | section | Issue → Document |
| `depends_on` | context | Entity → Component |
| `is_a` | category | Entity → Category |
| `has_component` | scope | Entity → Component |
| `produces_error` | frequency | Issue → ErrorCode |
| `related_to` | relation, weight | Fallback para predicados desconocidos |

### Mapas de routing

- `ENTITY_TYPE_TO_TAG`: 18 entradas mapeando `subject_type` → tag
- `PREDICATE_TO_EDGE`: 15 entradas mapeando `predicate` → edge
- `EDGE_DEFAULT_PROPS`: listas de propiedades por edge para generación de INSERT
- `TAG_INSERT_PROPS`: listas de propiedades por tag para generación de INSERT

`expand_from_graph` itera TODOS los 16 edge types bidireccionalmente, acepta filtro `relation_types` para restringir la travesía. Propiedades de vértice obtenidas vía `FETCH PROP ON` para tags `entity` e `issue`.

---

## 7. Modelo de datos en Qdrant

### Colección: `triplets`

- **Vectores**: 768d COSINE (`text-embedding-004`)
- **Point ID**: UUID (auto-generado por tripleta)
- **Upsert**: batches de 20 (`EMBEDDING_BATCH_SIZE`)

### Schema de payload

```
Identidad tripleta:  subject, predicate, object, subject_type, object_type
Vinculación grafo:   subject_id, object_id (IDs de vértice NebulaGraph)
Provenance:          source_doc, chunk_id, chunk_index, ingestion_batch, created_at
Namespace:           system, tenant_id, account_id, user_id
Estado:              is_active, memory_type, valid_from, valid_to, supersedes, superseded_by
Case metadata:       product, version, severity, channel, team, status
Fact metadata:       fact_type, confidence, stakeholder
```

### Payload indexes (14)

`source_doc`, `chunk_id`, `subject_id`, `object_id`, `system`, `account_id`, `tenant_id`, `user_id`, `is_active`, `fact_type`, `memory_type`, `product`, `version`, `severity`, `channel`

Creados lazy por `_ensure_payload_indexes()` en la primera init del cliente. Silenciosamente ignora excepciones — verificar logs si algún index parece faltar.

---

## 8. Memory Writer

`memory_writer.py` maneja el path de escritura para hechos del agente AM (solo Qdrant; escrituras a NebulaGraph pendientes Etapa 1B).

| Función | Efecto |
|---|---|
| `record_fact(subject, predicate, object_, system, account_id, fact_type, ...)` | Crea punto con `is_active=True`, auto-clasifica `memory_type`, retorna `fact_id` |
| `supersede_fact(old_fact_id, new_subject, new_predicate, new_object, ...)` | Llama `record_fact` para nuevo → `set_payload(valid_to, is_active=False, superseded_by)` en viejo |
| `write_facts_to_store(facts, system)` | Batch upsert, embed en grupos de 20 |

---

## 9. Account Store

`account_store.py` provee el estado estructurado autoritativo por cuenta, ensamblado desde queries a Qdrant:

```
load_account_state(account_id) → AccountState
  ├─ facts:        search_by_filter(fact_type="fact")
  ├─ stakeholders: search_by_filter(fact_type="stakeholder")
  └─ commitments:  search_by_filter(fact_type="commitment")
```

`AccountState` clasifica hechos por predicado en `objectives`, `risks`, `blockers`, `products_of_interest`:

| Predicado | Clasificación |
|---|---|
| `has_objective`, `objective_is`, `targets` | objectives |
| `has_risk`, `risk_is`, `at_risk` | risks |
| `blocked_by`, `has_blocker`, `blocker` | blockers |
| `interested_in`, `uses_product`, `evaluates` | products_of_interest |

`format_account_state()` produce la representación en texto que retorna la tool `get_account_state`.

---

## 10. Observabilidad

### Estructura de traces

Cada operación de retrieval e interacción de agente produce un `RetrievalTrace`:

| Fase | Origen | Campos |
|---|---|---|
| `tool:<name>` | Cada retrieval tool post-ejecución | query, candidates, top_scores, metadata de scope/filters |
| `agent:<name>` | Endpoint de agente post-interacción completa | answer_len, tool_calls (name+args), tool_count, session_id, duration_ms |
| `vector_search` | Pipeline de query directo | top_k, min_score, filters |
| `graph_traversal` | Pipeline de query directo | entity_count, hops |

Persistencia: JSONL en directorio `traces/`, un archivo por `trace_id`, una línea por fase. Múltiples fases por archivo (ej: una tool compuesta emite 2 líneas).

---

## 11. Runtime ADK

| Componente | Implementación | Persistencia |
|---|---|---|
| `LlmAgent` | `support_agent` / `account_manager_agent` | — |
| `SessionService` | `InMemorySessionService` | Se pierde al reiniciar |
| `ArtifactService` | `InMemoryArtifactService` | Se pierde al reiniciar |
| `MemoryService` | `InMemoryMemoryService` | Se pierde al reiniciar |
| `Runner` | Uno por agente, cacheado en dict `_runners` | — |

### Ciclo de vida de sesión

1. Endpoint recibe `question` + `session_id` opcional
2. `_ensure_session()` restaura existente o crea nueva
3. Runner invocado con `Content(role="user", parts=[Part(text=question)])`
4. Endpoint AM inyecta `account_id` vía parámetro `state_delta`
5. Eventos iterados; text parts recolectados como respuesta; tool calls extraídos para trace

### Atributos de Part

Los eventos ADK usan **snake_case**: `part.function_call`, `part.function_response` — no camelCase.

---

## 12. Superficie API

| Método | Endpoint | Handler |
|---|---|---|
| GET | `/api/v1/health` | Check de Qdrant + NebulaGraph + Gemini + ADK |
| POST | `/api/v1/ingest` | `ingest_document()` con metadata como form params |
| POST | `/api/v1/seed` | Carga `sample.txt` |
| POST | `/api/v1/query` | Pipeline directo: dense → graph → fuse → generate |
| POST | `/api/v1/query/stream` | Igual arriba, streaming SSE |
| GET | `/api/v1/documents` | Listar documentos ingeridos |
| DELETE | `/api/v1/documents/{filename}` | Eliminar documento |
| GET | `/api/v1/graph/stats` | Conteo de vértices + aristas |
| GET | `/api/v1/graph/entities` | Listar vértices |
| GET | `/api/v1/graph/edges` | Listar aristas |
| GET | `/api/v1/graph/subgraph` | Subgrafo desde entidad |
| GET | `/api/v1/graph/filters` | Valores de filtro disponibles |
| GET | `/api/v1/traces/` | Listar archivos de trace |
| GET | `/api/v1/traces/search` | Buscar traces por query |
| GET | `/api/v1/traces/{trace_id}` | Leer trace específico |
| GET | `/api/v1/artifacts/prompts` | Listar artifact de prompts |
| GET/POST | `/api/v1/artifacts/prompts/{name}` | Leer/crear prompt |
| GET/POST | `/api/v1/artifacts/playbooks/{name}` | Leer/crear playbook |
| POST | `/api/v1/agents/support/query` | Agente de soporte (sync) |
| POST | `/api/v1/agents/support/query/stream` | Agente de soporte (SSE) |
| POST | `/api/v1/agents/am/query` | Agente AM (sync), requiere `account_id` |
| POST | `/api/v1/agents/am/query/stream` | Agente AM (SSE), requiere `account_id` |
| GET | `/api/v1/agents/am/state/{account_id}` | Snapshot de estado de cuenta |

---

## 13. Evaluación

### Formato del truth set (`support_qa.jsonl`)

```json
{
  "question": "...",
  "relevant_keywords": [...],
  "relevant_chunks": [...],
  "relevance_scores": {},
  "product": "...",
  "ideal_answer": "..."
}
```

`relevant_chunks` se pobla post-ingesta vía `evals/populate_chunks.py`. La relevancia es keyword-based.

### Métricas actuales (25 preguntas, español, sample.txt)

| Métrica | Valor |
|---|---|
| relevance@5 | 1.0 |
| MRR | 1.0 |
| recall@5 | 0.73 |

---

## 14. Constraints clave

| Constraint | Detalle |
|---|---|
| Palabras reservadas nGQL | `timestamp` → usar `reported_at`; `index` → usar `chunk_index` |
| Valores string en NebulaGraph | Usar `.get_sVal().decode()`, no `.as_string()` |
| Sanitización de vertex ID | Máx 256 chars, alfanumérico + underscore + sufijo MD5 hash |
| Timing de creación de space | `USE graphrag` falla ~8s después de `CREATE SPACE`; init script reintenta 6× a intervalos de 3s |
| Persistencia de sesiones | InMemory — contexto conversacional se pierde al reiniciar; estado factual AM persiste en Qdrant |
| Alcance de memory_writer | Solo Qdrant — escrituras a NebulaGraph para facts AM son Etapa 1B |

---

## 15. Estructura del proyecto

```
app/
  agents/                    # Agentes Google ADK
    support_agent.py         #   LlmAgent, 6 tools (solo lectura)
    account_manager_agent.py #   LlmAgent, 10 tools (6 lectura + 4 escritura)
    base.py                  #   get_adk_model()
    artifacts.py             #   InMemoryArtifactService singleton
    prompts/
      support_system.py      #   Prompt grounded español (Resumen→Pasos→Evidencia→Incertidumbre)
      am_system.py           #   Prompt AM genérico (pendiente reescritura domain-specific)
    tools/
      retrieval_tools.py     #   6 tools de soporte + helper _trace()
      account_tools.py       #   10 tools de AM
  api/routes/                # Endpoints FastAPI
    agents.py                #   Endpoints de agentes + trace logging
    ingest.py                #   Upload + seed
    query.py                 #   Pipeline directo + streaming
    health.py                #   Health check
    documents.py             #   List/delete + graph stats
    graph.py                 #   Queries de grafo
    traces.py                #   Retrieval de traces
    artifacts.py             #   CRUD de prompts/playbooks
  core/
    genai.py                 #   Singleton LLM + embedding (batch=20, dims=768)
    retrieval.py             #   RetrievalEngine + traces + fuse
    graph.py                 #   Pool de conexiones NebulaGraph
    vectorstore.py           #   Singleton Qdrant + 14 payload indexes
    account_store.py         #   AccountState load/format
  pipelines/
    ingestion.py             #   Pipeline completo de ingesta (store dual)
    query.py                 #   Pipeline directo de consulta
    consolidation.py         #   classify → dedup → supersede
    memory_writer.py         #   record_fact / supersede_fact (solo Qdrant)
    loaders.py               #   Loaders PDF/TXT/MD
    text_splitter.py         #   RecursiveCharacterTextSplitter
  models/
    schemas.py               #   Modelos Pydantic (Triplet, AccountState, etc.)
    documents.py             #   Tipo Document
    graph_schema.py          #   Tags + edges + dicts de routing
  prompts/
    extraction.py            #   Prompts de extracción genérico + soporte
    qa.py                    #   Prompts QA system + user
evals/
  metrics.py                 #   relevance@k, MRR, nDCG, grounding, recall
  runner.py                  #   run_retrieval_eval, run_grounding_eval
  populate_chunks.py         #   Poblar relevant_chunks post-ingesta
  truth_sets/
    support_qa.jsonl         #   25 preguntas (español)
    am_continuity.jsonl      #   Escenarios AM (sin runner aún)
ui/
  app.py                     #   Entry point Streamlit
  pages/
    1_Upload.py              #   Upload con sidebar de metadata
    2_Graph.py               #   Visualización de grafo
    3_Query.py               #   Consulta por agente (support/AM)
    4_Documents.py           #   Lista de documentos
  components/
    api_client.py            #   Cliente HTTP + ingest_with_metadata()
    graph_renderer.py        #   Renderizado de grafo
    sidebar.py               #   Navegación
scripts/
  init_nebula.py             #   Init de schema (4 tags + 17 edges) con retry
  seed.py                    #   Carga sample.txt
test_data/
  sample.txt                 #   Datos seed (español, 3 errores de soporte)
tests/                       #   228 unit tests + 2 skipped
```
