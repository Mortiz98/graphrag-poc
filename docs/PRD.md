# PRD — GraphRAG: Memoria para dos sistemas agenciales

## 1. Propósito

Construir una plataforma de memoria híbrida (Qdrant + NebulaGraph + Google ADK) que sustente dos sistemas agenciales diferenciados:

- **Sistema A — Soporte virtual**: base de conocimiento corpus-centric para troubleshooting, incidentes y políticas.
- **Sistema B — Account Manager**: memoria longitudinal account-centric y temporal para continuidad relacional.

La plataforma comparte infraestructura, abstracciones y pipelines entre ambos sistemas, pero cada uno tiene su propia topología lógica, agentes y métricas.

---

## 2. Progreso actual

### Etapa 0 — Plataforma base: **COMPLETA**

| Entregable | Estado | Detalle |
|---|---|---|
| Runtime ADK | ✅ | `LlmAgent`, `Runner`, `SessionService`, `ArtifactService`, `MemoryService` conectados |
| Abstracción de retrieval | ✅ | `RetrievalEngine` con `search_dense`, `search_sparse` (stub), `search_hybrid` (stub), `search_by_filter`, `rerank` (stub), `get_supporting_chunks`, `log_trace` |
| Qdrant operativo | ✅ | Singleton thread-safe, colección `triplets`, COSINE 768d, 10 payload indexes |
| Contratos de identidad | ✅ | `system`, `tenant_id`, `account_id`, `user_id`, `session_id` en payload, scope y filtros |
| Provenance | ✅ | `source_doc`, `created_at`, `ingestion_batch`, `chunk_id`, `chunk_index` |
| Supersession | ✅ | `is_active` en payload, `active_only=True` por defecto en queries, `apply_supersession` marca `valid_to` + `is_active=False` |
| Deduplicación | ✅ | `deduplicate_against_existing` con coseno > 0.95, habilitada por defecto |
| Consolidación funcional | ✅ | Pipeline de 3 pasos (classify → dedup → supersede), resultados aplicados a ingesta |
| Stack LLM unificado | ✅ | `genai.generate()` / `genai.generate_stream()` único camino, legacy wrappers deprecados |
| Esquema de grafo de dominio | ✅ | Tags: `entity`, `issue`, `stakeholder`, `commitment`. Edges: `related_to`, `has_symptom`, `caused_by`, `resolved_by`, `affects`, `escalated_to`, `governed_by`, `reported_by`, `owns`, `responsible_for`, `affects_version`, `documented_in`, `depends_on`, `is_a`, `has_component`, `produces_error` |
| Evaluación | ✅ | Métricas IR implementadas, truth set con keyword-based relevance, runner funcional |
| UI Streamlit | ✅ | Upload, Graph, Query (agent select + streaming), Documents |

### Etapa 1A — MVP Soporte: **COMPLETA**

| Entregable | Estado | Detalle |
|---|---|---|
| Ingesta orientada a caso | ✅ | `SUPPORT_EXTRACTION_SYSTEM_PROMPT` con tipos Issue/Symptom/RootCause/Fix + fallback |
| Metadatos fuertes | ✅ | `CaseMetadata` (product, version, severity, channel, team, status); UI los expone |
| Dense retrieval | ✅ | `search_dense` funcional con filtros por metadatos |
| Grafo de dominio en ingesta | ✅ | `ENTITY_TYPE_TO_TAG` + `PREDICATE_TO_EDGE` routing; fallback a `entity`/`related_to`; 16 edges + 4 tags |
| Respuesta grounded | ✅ | Formato obligatorio: Resumen → Pasos → Evidencia → Incertidumbre; citación por source_doc |
| Prompt de agente domain-specific | ✅ | `SUPPORT_SYSTEM_PROMPT` en español con 6 tools documentadas y reglas de grounding |
| Retrieval tools enriquecidas | ✅ | 6 tools: search_knowledge_base, search_by_metadata, search_by_product, get_resolution_history, escalation_path, traverse_issue_graph |
| Logging de consultas | ✅ | `RetrievalTrace` por tool (phase `tool:<name>`) + trace global por interacción (phase `agent:support`) |
| Evaluación | ✅ | 25 preguntas en español; `populate_chunks.py`; métricas relevance/MRR/nDCG/recall/grounding |
| UI metadatos de ingesta | ✅ | System selector, Tenant ID, Account ID (AM), Case Metadata (Product, Version, Severity, Channel) |

### Etapa 1B — MVP Account Manager: **~40%**

| Entregable | Estado | Detalle |
|---|---|---|
| Session/state en ADK | ✅ | `InMemorySessionService`, `state_delta` para `account_id` |
| AccountStore autoritativo | ✅ | `AccountState` + `load_account_state()` + `format_account_state()` |
| Tools de lectura | ✅ | `get_account_state`, `get_commitments`, `get_stakeholder_map`, `search_episodes` |
| Tools de escritura | ✅ | `write_fact`, `update_fact`, `write_commitment`, `write_stakeholder` |
| Filtrado estructurado | ✅ | `search_by_filter` sin query sintética |
| AM system prompt | ⚠️ | Existe pero es genérico, sin protocolo de continuidad |
| ArtifactService conectado | ✅ | Cableado al Runner, pero sin tools de artifact en el agente |
| MemoryService conectado | ✅ | Cableado al Runner, pero sin contenido ni alimentación |
| Escritura en grafo | ❌ | `memory_writer` solo escribe a Qdrant, no a NebulaGraph |
| Prompt AM domain-specific | ❌ | Sin formato de respuesta, sin protocolo temporal |
| Evaluación AM | ❌ | `am_continuity.jsonl` existe pero no hay runner que procese su schema |

### Etapas 2–5: **No iniciadas**

---

## 3. Arquitectura de referencia

```
┌──────────────────────────────────────────────────────────┐
│  UI (Streamlit :8501)                                    │
│  Upload │ Graph │ Query (support/am select) │ Documents  │
├──────────────────────────────────────────────────────────┤
│  API (FastAPI :8000)                                     │
│  /ingest  /query  /query/stream  /agents/*  /traces      │
├──────────────────────────────────────────────────────────┤
│  Agents (Google ADK)                                     │
│  support_agent (6 tools)                                 │
│  account_manager_agent (10 tools: 6 read + 4 write)      │
│  SessionService ✅  ArtifactService ✅  MemoryService ✅  │
├──────────────────────────────────────────────────────────┤
│  Pipelines                                               │
│  ingestion → consolidation (aplica) → store dual         │
│  query → dense → graph → fuse → generate                │
│  memory_writer → record_fact / supersede_fact (Qdrant)  │
├──────────────────────────────────────────────────────────┤
│  Core                                                    │
│  genai (LLM+emb singleton)  │ retrieval engine           │
│  account_store (estado autoritativo)                     │
│  graph (NebulaGraph pool)   │ vectorstore (Qdrant single)│
├──────────────┬───────────────────────────────────────────┤
│   Qdrant      │   NebulaGraph                            │
│  triplets     │   entity, issue, stakeholder,            │
│  768d COSINE  │   commitment (tags)                     │
│  is_active    │   has_symptom, caused_by, resolved_by,   │
│  fact_type    │   affects, escalated_to, governed_by,   │
│  memory_type  │   reported_by, owns, responsible_for,   │
│  14 indexes   │   affects_version, documented_in,        │
│               │   depends_on, is_a, has_component,       │
│               │   produces_error (16 domain edges)       │
└──────────────┴───────────────────────────────────────────┘
```

---

## 4. Etapa 1A — MVP de soporte virtual

### Objetivo

Responder preguntas de soporte con grounding y trazabilidad. El agente debe poder resolver consultas típicas de troubleshooting sobre un corpus de tickets, artículos y playbooks.

### 4.1 store_in_graph con tags/edges de dominio — **COMPLETADO**

**Implementación**:

- `ENTITY_TYPE_TO_TAG` dict mapea subject_type → tag (Issue → tag `issue`, resto → `entity`)
- `PREDICATE_TO_EDGE` dict mapea predicate → edge (has_symptom → edge `has_symptom`, desconocido → `related_to`)
- `_build_vertex_insert()` genera INSERT con props del tag (issue: name/severity/product/version/channel; entity: name/type/description)
- `_build_edge_insert()` genera INSERT con props del edge (domain edges usan `EDGE_DEFAULT_PROPS`; related_to usa `relation` + `weight`)
- Fallback automático: si INSERT con tag domain falla, reintentar con `entity`; si edge domain falla, reintentar con `related_to`
- 6 edges nuevos agregados: `affects_version`, `documented_in`, `depends_on`, `is_a`, `has_component`, `produces_error`
- `expand_from_graph` ahora itera TODOS los edge types (16), soporta `relation_types` filter, y FETCH PROP en `entity` + `issue`

**Criterio de aceptación**: ✅ `make seed` → nGQL `MATCH (n:issue) RETURN n.name` muestra QDRANT_CONNECTION_TIMEOUT, etc.

### 4.2 Respuesta grounded del agente de soporte — **COMPLETADO**

**Implementación**:

- `SUPPORT_SYSTEM_PROMPT` reescrito en español con formato obligatorio:
  - Resumen → Pasos sugeridos → Evidencia (con `[fuente: <source_doc>]`) → Incertidumbre
- Reglas de grounding: solo claims respaldados por retrieval; si no hay evidencia, decirlo
- 6 tools documentadas en el prompt con instrucciones de cuándo usar cada una
- `traverse_issue_graph` ahora incluye `[fuente: ...]` en output (source_doc o "grafo")

**Criterio de aceptación**: ✅ Consultar al agente y recibir respuesta con sección Evidencia que cita documentos.

### 4.3 Retrieval tools enriquecidas para soporte — **COMPLETADO**

**Implementación**:

- `search_by_product(product, version=None, top_k=10)`: filtro estructural en Qdrant (search_by_filter), sin embedding
- `get_resolution_history(issue_description, top_k=5)`: dense search → expand_from_graph(relation_types=["resolved_by", "caused_by"])
- `escalation_path(issue_description, top_k=5)`: dense search → expand_from_graph(relation_types=["escalated_to", "governed_by"])
- Support agent: 3 → 6 tools registrado en `support_agent.py`

**Criterio de aceptación**: ✅ El agente puede responder "¿Cómo resuelvo el error de timeout?" usando get_resolution_history.

### 4.4 Truth set de evaluación con datos reales — **COMPLETADO**

**Implementación**:

- `sample.txt` traducido al español con 3 errores de soporte (QDRANT_CONNECTION_TIMEOUT, NEBULA_SESSION_POOL_EXHAUSTED, TRIPLET_EXTRACTION_FAILED) con estructura completa: síntomas, causa raíz, fix, playbook, equipo de escalación, política
- `support_qa.jsonl` con 25 preguntas en español (6 conocimiento general + 3 por error + 3 escalación + 2 playbooks + 11 variadas)
- `populate_chunks.py` script para poblar `relevant_chunks` post-ingesta
- Qdrant payload indexes: 14 (agregados product, version, severity, channel)

**Criterio de aceptación**: ✅ 25 preguntas en truth set; `run_retrieval_eval` funciona contra datos reales.

### 4.5 UI: exponer metadatos de ingesta en Upload — **COMPLETADO**

**Implementación**:

- Sidebar con System selector (Soporte/AM), Tenant ID, Account ID (condicional a AM)
- Case Metadata expander (Product, Version, Severity, Channel) condicional a Soporte
- `ApiClient.ingest_with_metadata()` envía metadata como Form params
- Endpoint `/ingest` ya aceptaba todos los params — gap era solo UI

**Criterio de aceptación**: ✅ Subir archivo como AM con account_id y verificar en Qdrant.

---

## 5. Etapa 1B — MVP de Account Manager

### Objetivo

Mantener continuidad útil a lo largo de sesiones, con estado de cuenta autoritativo, memoria episódica y capacidad de escribir hechos.

### 5.1 Escritura en grafo desde memory_writer

**Problema actual**: `memory_writer.py` solo escribe a Qdrant. Los hechos escritos por el AM no tienen representación en NebulaGraph.

**Especificación**:

- `record_fact` debe además crear vértice y arista en NebulaGraph:
  - Vértice con tag `stakeholder` o `commitment` según `fact_type`
  - Arista `owns` o `responsible_for` según corresponda
- `supersede_fact` debe actualizar la propiedad del vértice en NebulaGraph (marcar como superseded)
- Si NebulaGraph no está disponible, la escritura a Qdrant debe proceder (grafo es best-effort)

**Archivos**: `app/pipelines/memory_writer.py`

**Criterio de aceptación**: Después de `write_fact` con `fact_type="commitment"`, verificar con nGQL que existe un vértice con tag `commitment` en NebulaGraph.

### 5.2 AM system prompt domain-specific

**Problema actual**: El prompt es genérico (4 lineas de guía). No hay protocolo de continuidad, ni formato de respuesta, ni instrucciones sobre cuándo escribir vs leer.

**Especificación**:

- El prompt debe incluir:
  - Protocolo: "Siempre llama `get_account_state` antes de responder"
  - Formato de respuesta:
    ```
    ## Account Overview
    <1-2 sentence summary of account state>

    ## Key Facts
    - <fact> (since: <valid_from>)

    ## Open Commitments
    - <commitment> (owner: <owner>, due: <due_date>)

    ## Stakeholders
    - <name>: <role>

    ## Recommendation
    <suggested next action, if any>
    ```
  - Cuándo escribir: "Si el usuario menciona un hecho nuevo, compromiso, o cambio, úsa la tool correspondiente"
  - Cuándo actualizar: "Si un hecho cambia, usa `update_fact` en vez de `write_fact`"
  - Tono: profesional, conciso, sin inventar datos

**Archivos**: `app/agents/prompts/am_system.py`

**Criterio de aceptación**: Preguntar "What do you know about acme_corp?" y recibir respuesta con las secciones del formato.

### 5.3 Tools adicionales para AM

**Problema actual**: No hay tool para registrar riesgos, objetivos, bloqueadores explícitamente. No hay tool para consultas temporales.

**Especificación**: Agregar tools:

- `write_risk(subject, risk_description, account_id)`: registra un riesgo con `fact_type="fact"` y predicado `has_risk`
- `write_objective(subject, objective, account_id)`: registra un objetivo con predicado `targets`
- `write_blocker(subject, blocker_description, account_id)`: registra un blocker con predicado `blocked_by`
- `what_changed_since(account_id, since_date)`: busca hechos con `created_at` o `valid_from` > since_date usando `search_by_filter` + filtro de rango (requiere index de timestamp)

**Archivos**: `app/agents/tools/account_tools.py`, `app/agents/account_manager_agent.py`

**Criterio de aceptación**: El agente puede responder "What risks does acme_corp have?" y mostrar riesgos registrados previamente.

### 5.4 Runner de evaluación AM

**Problema actual**: `am_continuity.jsonl` tiene schema distinto (scenario_id, expected_facts, expected_commitments) y no hay runner que lo procese.

**Especificación**:

- Crear `run_am_continuity_eval(truth_set_path)` que:
  - Carga escenarios desde JSONL
  - Para cada escenario, llama a `get_account_state(account_id)`
  - Verifica que `expected_facts` estén presentes en el estado
  - Verifica que `expected_commitments` estén presentes
  - Calcula fact_recall, commitment_recall, y overall_continuity_score
- Crear datos de prueba AM: ingesta de datos de ejemplo para ACC-1 y ACC-2

**Archivos**: `evals/runner.py`, `evals/truth_sets/am_continuity.jsonl` (actualizar con datos coherentes), `test_data/am_data/` (datos de ejemplo)

**Criterio de aceptación**: `run_am_continuity_eval` contra los datos de ejemplo produce fact_recall > 0.5.

### 5.5 Artifact tools para AM

**Problema actual**: ArtifactService está conectado al Runner pero el agente no tiene tools para leer/escribir artifacts (reportes, presentaciones, propuestas).

**Especificación**:

- Agregar tools:
  - `save_artifact(account_id, artifact_name, content)`: guarda un artifact por cuenta
  - `load_artifact(account_id, artifact_name)`: carga un artifact por cuenta
  - `list_artifacts(account_id)`: lista artifacts de una cuenta
- Usar `ArtifactService` del Runner (ya conectado)

**Archivos**: `app/agents/tools/artifact_tools.py` (nuevo), `app/agents/account_manager_agent.py`

**Criterio de aceptación**: El agente puede guardar y recuperar un reporte para una cuenta.

---

## 6. Etapa 2 — Hardening de retrieval

### Objetivo

Mejorar la calidad de retrieval antes de añadir complejidad de grafo avanzado.

### 6.1 Sparse retrieval real

**Problema actual**: `search_sparse` es stub que delega a `search_dense`.

**Especificación**:

- Configurar sparse vectors en Qdrant (BM25-like)
- Crear colección con named vectors: `dense` (768d) + `sparse` (BM25 token-level)
- Implementar `search_sparse` con Qdrant sparse search
- En ingesta, generar sparse vectors junto con dense vectors

**Archivos**: `app/core/retrieval.py`, `app/core/vectorstore.py`, `app/pipelines/ingestion.py`

**Criterio de aceptación**: `search_sparse("error code ERR-503")` encuentra documentos que contengan "ERR-503" exactamente, incluso si el dense retrieval no los encontró.

### 6.2 Hybrid retrieval con fusión server-side

**Problema actual**: `search_hybrid` es stub.

**Especificación**:

- Usar `query_points` con `prefetch` para dense + sparse fusion
- Implementar RRF (Reciprocal Rank Fusion) o Qdrant built-in hybrid
- `search_hybrid` debe combinar dense + sparse con pesos configurables

**Archivos**: `app/core/retrieval.py`

**Criterio de aceptación**: Hybrid retrieval supera a dense-only en relevance@5 contra el truth set.

### 6.3 Reranking

**Problema actual**: `rerank` es noop passthrough.

**Especificación**:

- Implementar reranking con LLM (Gemini) o cross-encoder
- El reranker reordena los top_k candidatos basándose en relevancia fine-grained
- Alternativa: usar `genai.generate()` para puntuar cada candidato vs query

**Archivos**: `app/core/retrieval.py`

**Criterio de aceptación**: Reranked results mejoran MRR vs unranks en el truth set.

### 6.4 Query rewriting / expansión

**Especificación**:

- Antes de retrieval, expandir la query del usuario con términos relacionados
- Usar Gemini para generar 2-3 variaciones de la query
- Buscar con cada variación y fusionar resultados

**Archivos**: `app/pipelines/query.py`

**Criterio de aceptación**: Queries vagas como "it's broken" obtienen mejores resultados tras expansión.

---

## 7. Etapa 3A — Grafo de dominio para soporte

### Objetivo

Capturar relaciones útiles entre incidentes, causas, fixes y entidades del dominio, y usarlas para retrieval asistido por grafo.

### 7.1 Graph-assisted retrieval

**Especificación**:

- Cuando una query menciona un Issue conocido, expandir por `has_symptom` → `caused_by` → `resolved_by`
- Integrar resultados del grafo en el contexto del agente como "related paths"
- El agente debe poder mostrar cadenas causales: "Issue X → caused by Y → resolved by Z"

**Archivos**: `app/agents/tools/retrieval_tools.py`, `app/core/retrieval.py` (nuevo método `search_with_graph_expansion`)

**Criterio de aceptación**: Preguntar "Why am I getting timeout errors?" y recibir respuesta que traza Issue → RootCause → Fix.

### 7.2 Multi-hop traversal en la UI

**Especificación**:

- Página Graph: agregar "Path between entities" con búsqueda de camino más corto
- Mostrar cadenas causales visualmente en el graph renderer

**Archivos**: `ui/pages/2_Graph.py`, `app/api/routes/graph.py` (nuevo endpoint `graph/path`)

---

## 8. Etapa 3B — Grafo temporal para Account Manager

### Objetivo

Mejorar razonamiento relacional e histórico sobre cuentas.

### 8.1 Modelo de cuenta en NebulaGraph

**Especificación**:

- Crear vértices con tag `stakeholder` para cada persona, con propiedades `role`, `account_id`, `since`
- Crear edges `owns` (stakeholder → commitment), `responsible_for` (stakeholder → issue)
- Crear edges con propiedades temporales: `valid_from`, `valid_to`
- Consultas temporales: "qué cambió desde la última renovación"

**Archivos**: `app/pipelines/memory_writer.py`, `app/core/retrieval.py`

**Criterio de aceptación**: Preguntar "Who was the decision maker for acme_corp 3 months ago?" y obtener respuesta correcta.

### 8.2 Supersession estructurada en grafo

**Especificación**:

- Cuando un hecho se supersedé, marcar el vértice/arista en NebulaGraph con `valid_to`
- Las consultas de grafo deben poder filtrar por vigencia

**Archivos**: `app/pipelines/memory_writer.py`, `app/core/retrieval.py`

---

## 9. Etapa 4 — Carriles experimentales

### Objetivo

Probar mejoras de retrieval sin comprometer estabilidad.

### 9.1 Shadow mode

**Especificación**:

- Configuración de lane: `control` (dense), `experiment_a` (hybrid), `experiment_b` (multi-vector)
- Cada query se ejecuta en el lane control + lane experimental
- Se registran métricas de ambos lanes en traces
- El usuario solo ve resultados del lane control

**Archivos**: `app/core/retrieval.py`, `app/pipelines/query.py`, `app/api/routes/query.py`

### 9.2 Sticky cohorts

**Especificación**:

- Hash determinista de `account_id` o `tenant_id` → lane
- Cada cuenta permanece en el mismo lane establemente
- Permite comparación justa entre lanes

### 9.3 Lane multi-vector local

**Especificación**:

- Configurar named vectors en Qdrant para multi-vector (ColBERT-like)
- Generar multi-vectors durante ingesta
- Implementar `search_multivector` en RetrievalEngine

### 9.4 POC Graphiti para AM (condicional)

**Especificación**:

- Solo si hay señal de: alta tasa de hechos stale, errores de continuidad, mala supersession
- Evaluar Graphiti como benchmark comparativo contra la implementación actual
- No como base del sistema, sino como experimento controlado

---

## 10. Etapa 5 — Managed y escalado

### 10.1 Decisión de deployment

- Self-hosted (actual) vs Qdrant Cloud vs Milvus/Zilliz Cloud
- Criterios: volumen, latencia, costo operacional, SLA

### 10.2 ArtifactService persistente

**Problema actual**: `InMemoryArtifactService` pierde todo al reiniciar.

**Especificación**: Implementar `FileArtifactService` o usar DB-backed service que persista artifacts a disco o Qdrant.

**Archivos**: `app/agents/artifacts.py`

### 10.3 SessionService persistente

**Problema actual**: `InMemorySessionService` pierde sesiones al reiniciar.

**Especificación**: Evaluar `DatabaseSessionService` de ADK o implementar custom que persista a SQLite/Postgres.

### 10.4 Seguridad y multi-tenancy

- Auth en API endpoints
- Aislamiento por tenant_id en queries (ya soportado por scope, falta enforcement)
- Rate limiting

---

## 11. Métricas por sistema

### Soporte (Sistema A)

| Métrica | Cómo medirla | Target MVP | Target Etapa 2 |
|---|---|---|---|
| relevance@5 | Truth set + retrieval eval | > 0.3 | > 0.5 |
| MRR | Truth set | > 0.4 | > 0.6 |
| Grounding rate | Overlap respuesta vs evidencia | > 0.5 | > 0.7 |
| Latencia p95 | Instrumentación API | < 5s | < 3s |
| Contención | Feedback usuario | baseline | > 50% |

### Account Manager (Sistema B)

| Métrica | Cómo medirla | Target MVP | Target Etapa 3B |
|---|---|---|---|
| Fact recall | AM continuity eval | > 0.5 | > 0.8 |
| Stale error rate | AM continuity eval | < 30% | < 10% |
| Commitment recall | AM continuity eval | > 0.5 | > 0.8 |
| Stakeholder attribution | AM continuity eval | > 0.6 | > 0.9 |
| Latencia p95 | Instrumentación API | < 5s | < 3s |

---

## 12. Deuda técnica conocida

| Item | Impacto | Prioridad |
|---|---|---|
| `apply_supersession` nunca testeado sin mock | Puede fallar con datos reales | Alta (pre-1A) |
| `memory_writer` no escribe a grafo | AM writes invisibles en NebulaGraph | Alta (1B) |
| `_ensure_payload_indexes` traga excepciones | Indexes pueden faltar silenciosamente | Media |
| `store_in_graph` usa domain routing | ✅ Resuelto — ENTITY_TYPE_TO_TAG + PREDICATE_TO_EDGE con fallback | Hecho (1A) |
| `search_sparse` y `search_hybrid` son stubs | Sin BM25, sin términos exactos | Alta (Etapa 2) |
| `rerank` es noop | Retrieval subóptimo | Media (Etapa 2) |
| `InMemorySessionService` pierde sesiones | No hay persistencia entre reinicios | Media (Etapa 5) |
| `InMemoryArtifactService` pierde artifacts | No hay persistencia entre reinicios | Media (Etapa 5) |
| Streaming endpoint duplica lógica de pipeline | Mantenimiento duplicado | Baja |
| `_sanitize_vertex_id` causa colisiones | "ACME Corp" = "ACME_Corp" | Media |
| `get_filters` escanea todos los puntos | O(n) sin paginación | Baja |
| `delete_document` escanea toda la colección | O(n) para contar referencias | Baja |
| `am_state` bypassa el agente | Inconsistencia de comportamiento | Baja |
| No hay auth en endpoints | Cualquiera puede escribir/leer | Etapa 5 |
| Legacy `llm.py` y `embeddings.py` eliminados | ✅ Resuelto — eliminados, todas las importaciones migradas a genai | Hecho (1A) |

---

## 13. Tests faltantes

| Área | Coverage actual | Mínimo requerido |
|---|---|---|
| `apply_supersession` real | 0 (siempre mockeado) | 1 test con Qdrant mockeado pero lógica real |
| Agent endpoints | 0 | 1 test de sync, 1 test de session lifecycle |
| Streaming SSE | 0 | 1 test de formato de eventos |
| `search_by_filter` | ✅ 1 test | Hecho |
| `expand_from_graph` | ✅ 2 tests (empty + success + failed) | Hecho |
| `account_store` | 0 | 1 test de load + format |
| Write tools AM | 0 (solo unit con mock) | 1 test de side effect en Qdrant mock |
| Artifact tools | 0 | 1 test de save + load |
| `fuse_results` | ✅ 5 tests | Hecho |
| Consolidation end-to-end | 0 | 1 test de ingest → dedup → supersede → verify payload |
| Domain routing store_in_graph | ✅ 4 tests | Hecho |
| Build vertex/edge insert | ✅ 8 tests | Hecho |
| All 6 retrieval tools | ✅ 10 tests | Hecho |
| `_extract_tool_calls` | ✅ 3 tests | Hecho |
| `_log_interaction` | ✅ 1 test | Hecho |

---

## 14. Orden de construcción recomendado

```
Etapa 0 ████████████████████ 100%  COMPLETA

Etapa 1A ████████████████████ 100%  COMPLETA
  4.1 store_in_graph con dominio      ✅
  4.2 Respuesta grounded              ✅
  4.3 Retrieval tools enriquecidas    ✅
  4.4 Truth set real                  ✅
  4.5 UI metadatos de ingesta         ✅

Etapa 1B ────────────── 40%
  5.1 Escritura en grafo
  5.2 AM prompt domain-specific
  5.3 Tools adicionales AM
  5.4 Runner evaluación AM
  5.5 Artifact tools

Etapa 2 ──── 10%
  6.1 Sparse retrieval
  6.2 Hybrid retrieval
  6.3 Reranking
  6.4 Query rewriting

Etapa 3A 0%
  7.1 Graph-assisted retrieval
  7.2 Multi-hop en UI

Etapa 3B 0%
  8.1 Modelo de cuenta en grafo
  8.2 Supersession en grafo

Etapa 4 0%
  9.1 Shadow mode
  9.2 Sticky cohorts
  9.3 Multi-vector
  9.4 Graphiti POC

Etapa 5 0%
  10.1 Deployment decision
  10.2 ArtifactService persistente
  10.3 SessionService persistente
  10.4 Seguridad
```

---

## 15. No hacer

- No construir un pipeline GraphRAG completo (community detection, reportes jerárquicos) hasta que haya corpus amplio y necesidad demostrada
- No introducir Graphiti como dependencia del MVP
- No reemplazar Qdrant dense retrieval por Wholembed v3 como baseline
- No añadir Milvus/Zilliz hasta que haya razón estratégica clara
