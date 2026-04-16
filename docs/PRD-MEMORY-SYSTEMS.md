# PRD: Sistemas de Memoria Agentiva — Soporte Virtual y Account Manager

## 1. Resumen ejecutivo

Este documento define el plan de desarrollo para dos sistemas de memoria agentiva que comparten plataforma base pero difieren en topología lógica:

1. **Sistema A — Base de conocimiento para soporte virtual**: Recupera y sintetiza conocimiento sobre incidentes, síntomas, causas, resoluciones, políticas y procedimientos a partir de transcripciones, tickets, artículos de ayuda y playbooks.

2. **Sistema B — Memoria longitudinal para Account Manager**: Sostiene continuidad relacional y operativa a lo largo de meses, preservando hechos vigentes, episodios pasados, compromisos abiertos, cambios de contexto y relaciones entre actores.

Ambos sistemas se construyen sobre **Google ADK** como runtime agentivo, **Qdrant** como store vectorial principal, y **NebulaGraph** como capa de grafo. FastAPI se mantiene como backend de servicios exponiendo APIs REST.

---

## 2. Objetivos y criterios de éxito

| # | Objetivo | Criterio de éxito |
|---|----------|-------------------|
| O1 | Plataforma base compartida operativa | Qdrant + NebulaGraph + ADK + FastAPI corriendo con `make run`, health checks verdes |
| O2 | MVP Soporte funcional | Agente de soporte responde preguntas con grounding y trazabilidad, retrieval dense con filtros de dominio, evaluación baseline > 0.6 relevance@5 |
| O3 | MVP Account Manager funcional | Agente de AM mantiene estado de cuenta, recupera hechos vigentes y episodios, continuidad entre sesiones demostrable |
| O4 | Retrieval hardened | Sparse + hybrid + reranking operativos, métricas de evaluación continuas |
| O5 | Grafo de dominio operativo | Schemas de NebulaGraph por dominio, consulta multi-hop con filtros |
| O6 | Evaluación continua | Truth set, métricas automatizadas, A/B testing de estrategias de retrieval |

---

## 3. Stack tecnológico

| Componente | Tecnología | Rol |
|---|---|---|
| Runtime agentivo | **Google ADK** | Session, state, MemoryService, ArtifactService, callbacks, agentes |
| LLM | **OpenRouter** (GPT-4o-mini default) | Extracción, generación, razonamiento |
| Embeddings | **OpenRouter** (text-embedding-3-small, 1536d) | Dense retrieval |
| Vector DB | **Qdrant** (self-hosted, Docker) | Dense, sparse, hybrid, multivector retrieval |
| Graph DB | **NebulaGraph** (v3, Docker) | Relaciones, multi-hop, temporalidad |
| API | **FastAPI** | Backend de servicios REST |
| UI | **Streamlit** (existente) | Interfaz interactiva de demo |
| Observabilidad | **structlog** | Logging estructurado |
| Infra | **Docker Compose** | Orquestación de servicios |
| Evaluación | **Pytest + custom evals** | Truth sets, métricas automatizadas |

### Decisiones arquitectónicas confirmadas

| Decisión | Confirmada | Detalle |
|---|---|---|
| Runtime agentivo | Google ADK | Se adopta como runtime principal. FastAPI permanece como API de servicios |
| Orden de MVPs | Por etapas del plan | Etapa 0 → 1A (Soporte) y 1B (AM) → 2 → 3A/3B → 4 → 5 |
| Qdrant como retrieval inicial | Si | Dense primero, luego sparse/hybrid |
| NebulaGraph para relaciones | Si | Solo cuando el caso de uso lo justifique |
| Abstracción de retrieval | Si | Desde día uno, interfaz interna desacoplada |
| Graphiti | No en MVP | Benchmark experimental posterior |
| Wholembed v3 | No en MVP | Lane experimental posterior |

---

## 4. Principios rectores del documento original

Los siguientes principios guían todas las decisiones de este PRD y provienen del análisis de arquitectura de memoria que originó el proyecto.

### 4.1 Veredictos por sistema

**Sistema A — Soporte virtual:**
- **Qdrant primero.** El mayor retorno inicial viene de retrieval robusto con buen grounding, no de un grafo complejo desde el día uno.
- **NebulaGraph después.** El grafo aporta valor cuando la consulta deja de ser solo similitud textual y pasa a ser relacional (root causes conectados a síntomas, fixes asociados a familias de incidentes).
- **GraphRAG selectivo y no omnipresente.** No meter un pipeline completo de extracción de entidades global, community detection y reportes jerárquicos desde el inicio.

**Sistema B — Account Manager:**
- **ADK + estado estructurado + memoria episódica desde el inicio.** La unidad dominante no es el documento, sino la cuenta y su evolución.
- **Qdrant como store principal de episodios y retrieval.** Los hechos vigentes y los episodios se recuperan bajo demanda, no se cargan todos al contexto.
- **NebulaGraph cuando la complejidad relacional y temporal dé retorno claro.** Múltiples stakeholders, cambios de ownership, compromisos que expiran.
- **Graphiti como benchmark o POC tardío, no como base inicial.** Conceptualmente valioso pero desalineado con NebulaGraph como backend.

### 4.2 Taxonomía de memoria (compartida por ambos sistemas)

Ambos sistemas necesitan separar cuatro tipos de información. La diferencia no está en si los usan, sino en cuáles pesan más y cómo se recuperan.

| Tipo de memoria | Descripción | Peso en Sistema A | Peso en Sistema B | Almacenamiento |
|---|---|---|---|---|
| **Estado actual estructurado** | Lo vigente y autoritativo. Hechos ciertos ahora. | Medio (estado de caso, versión actual) | Alto (estado de cuenta, compromisos abiertos) | Session state (ADK) + Qdrant (hechos con `valid_to=None`) |
| **Memoria episódica** | Eventos, reuniones, hitos, conversaciones, decisiones. | Bajo (casos pasados como contexto) | Alto (reuniones, cambios de postura, promesas) | Qdrant (embeddings de episodios) |
| **Memoria semántica documental** | Conocimiento del corpus. Artículos, playbooks, políticas. | Alto (corpus de soporte) | Medio (documentos de cuenta, contratos) | Qdrant (chunks + triplets) |
| **Memoria procedural** | Prompts, reglas, playbooks y políticas de ejecución. | Alto (playbooks de resolución) | Medio (reglas de negocio, políticas de renovación) | ADK ArtifactService + Qdrant (tag: `procedural`) |

En el runtime ADK esto se traduce en:
- `Session/state` → memoria de trabajo (pequeña, siempre disponible)
- `MemoryService` → memoria archival (grande, consultada bajo demanda)
- `ArtifactService` → documentos, reportes y evidencias persistentes

### 4.3 Pipeline común de consolidación

Ambos sistemas comparten un pipeline común de escritura y mantenimiento de memoria, aplicable tanto a ingesta de documentos como a registro de hechos episódicos:

1. **Capturar** interacción o documento
2. **Extraer candidatos** de memoria (triplets, facts, episodes)
3. **Clasificar por tipo** (estado estructurado | episódico | semántico documental | procedural)
4. **Consolidar y deduplicar** contra memoria existente
5. **Aplicar supersession** cuando algo reemplaza un hecho anterior
6. **Registrar provenance** (fuente, fecha, batch, confianza)
7. **Permitir recuperación selectiva** según contexto (cuenta, caso, vigencia)

Este pipeline se implementa en `app/pipelines/consolidation.py` (nuevo) y es invocado tanto desde la ingesta de documentos (Sistema A) como desde el registro de hechos (Sistema B).

### 4.4 Orden de construcción

El orden recomendado **no** es "máxima sofisticación desde el día uno", sino "máximo aprendizaje útil por capa":

1. **Retrieval y continuidad funcional** (Fase 0 + 1A/1B)
2. **Calidad** (Fase 2: hybrid, reranking, evaluación)
3. **Grafo** (Fase 3A/3B: relaciones y temporalidad)
4. **Temporalidad avanzada** (Fase 3B: supersession, vigencia)
5. **Experimentos managed** (Fase 4: Wholembed, Graphiti)
6. **Optimización** (Fase 5: managed, escalado)

Este orden reduce riesgo, acorta el camino al primer valor, y deja abierta la evolución sin hipotecar el MVP.

### 4.5 Ruta de evolución del retrieval

El documento especifica tres lanes de retrieval:

| Lane | Tipo | Tecnología | Cuándo |
|---|---|---|---|
| **A (Control)** | Dense retrieval → dense+sparse → hybrid | Qdrant native | Fase 0-2 |
| **B (Experimento local)** | Multi-vector con late interaction | Qdrant multivectors + ColBERT | Fase 4 |
| **C (Experimento managed)** | Wholembed v3 como sidecar | Mixedbread API | Fase 4, cohorte limitada |

La capa de abstracción de retrieval (Fase 0.2) desacopla la aplicación de los detalles del motor, permitiendo migrar entre lanes sin refactor profundo.

---

## 5. Arquitectura de sistema

### 5.1 Vista general

```
                     ┌─────────────────────────────────────────┐
                     │           Google ADK Runtime             │
                     │  ┌─────────────┐  ┌──────────────────┐ │
                     │  │ Agent Soporte│  │  Agent AM        │ │
                     │  │ (Session,    │  │ (Session,        │ │
                     │  │  state,      │  │  state,          │ │
                     │  │  memory)     │  │  memory)         │ │
                     │  └──────┬───────┘  └───────┬──────────┘ │
                     │         │                   │            │
                     │  ┌──────┴───────────────────┴──────┐    │
                     │  │        Shared Services           │    │
                     │  │  MemoryService │ ArtifactService │    │
                     │  │  Callbacks      │ Evaluation      │    │
                     │  └──────────────┬──────────────────┘    │
                     └─────────────────┼───────────────────────┘
                                       │
                     ┌─────────────────┼───────────────────────┐
                     │          FastAPI API Layer               │
                     │  /ingest  /query  /documents  /graph     │
                     │  /memory  /account  /eval                 │
                     └────────┬─────────────────┬───────────────┘
                              │                 │
              ┌───────────────┼─────────────────┼───────────────┐
              │               ▼                 ▼               │
              │        ┌──────────────┐  ┌──────────────┐       │
              │        │   Qdrant     │  │ NebulaGraph  │       │
              │        │ (vectors +   │  │ (knowledge   │       │
              │        │  payloads)   │  │  graph)      │       │
              │        └──────────────┘  └──────────────┘       │
              │              Retrieval Engine                    │
              │         (abstraction layer)                       │
              └─────────────────────────────────────────────────┘
                              │
                              ▼
                     ┌──────────────┐
                     │  OpenRouter   │
                     │ (LLM + Emb)   │
                     └──────────────┘
```

### 5.2 Flujo de datos — Sistema A (Soporte)

```
Documento / Ticket / Artículo
         │
         ▼
    ┌──────────┐    ┌────────────┐    ┌──────────────────┐
    │  Loader  │───▶│  Chunker   │───▶│  Extractor (LLM) │
    └──────────┘    └────────────┘    └────────┬─────────┘
                                               │
                                    ┌──────────┴──────────┐
                                    │  Triplet + Metadata  │
                                    │  (case_id, product,  │
                                    │   severity, version) │
                                    └──────────┬──────────┘
                                               │
                          ┌────────────────────┴────────────────────┐
                          ▼                                         ▼
                  ┌──────────────┐                         ┌──────────────┐
                  │   Qdrant     │                         │ NebulaGraph  │
                  │  (dense +    │                         │ (generic +  │
                  │   metadata)  │                         │  domain)     │
                  └──────┬───────┘                         └──────┬───────┘
                         │                                         │
                         └──────────────┬──────────────────────────┘
                                        ▼
                              ┌──────────────────┐
                              │ Retrieval Engine   │
                              │ (dense → hybrid)  │
                              └────────┬──────────┘
                                        │
                                        ▼
                              ┌──────────────────┐
                              │  Agent Soporte   │
                              │  (ADK Session)   │
                              │  → grounded QA   │
                              └──────────────────┘
```

### 5.3 Flujo de datos — Sistema B (Account Manager)

```
Interacción (reunión, chat, email)
         │
         ▼
    ┌──────────────────────────────────────────────┐
    │           Extractor + Classifier (LLM)         │
    │  → Facts (vigentes)                            │
    │  → Episodes (eventos)                          │
    │  → Commitments (compromisos)                   │
    │  → Stakeholders (personas, roles)              │
    └──────────────────────┬─────────────────────────┘
                           │
              ┌────────────┴────────────────┐
              ▼                              ▼
    ┌──────────────────┐          ┌──────────────────┐
    │  Qdrant           │          │  Qdrant           │
    │  (episodes +      │          │  NebulaGraph      │
    │   facts vectors)  │          │  (account model   │
    └────────┬───────────┘          │   + stakeholders) │
             │                      └────────┬──────────┘
             │                               │
             └───────────────┬───────────────┘
                             ▼
                   ┌──────────────────┐
                   │  Agent AM         │
                   │  (ADK Session     │
                   │   + account state)│
                   │  → continuity     │
                   └──────────────────┘
```

---

## 6. Modelo de datos

### 6.1 Modelo unificado de retrieval (Qdrant)

Cada punto en Qdrant tendrá los siguientes campos base, extendidos según el sistema:

```python
# Campos base (compartidos)
{
    "id": UUID,
    "vector": list[float],           # 1536d cosine
    "payload": {
        # Identidad
        "system": str,               # "support" | "am"
        "tenant_id": str | None,
        "account_id": str | None,

        # Triplet (genérico, usado en Sistema A)
        "subject": str,
        "predicate": str,
        "object": str,
        "subject_id": str,
        "object_id": str,
        "subject_type": str,
        "object_type": str,

        # Provenance
        "source_doc": str,
        "chunk_id": str,
        "chunk_index": int,
        "created_at": str,           # ISO 8601
        "ingestion_batch": str,

        # Sistema A — Metadatos de caso
        "case_id": str | None,
        "product": str | None,
        "version": str | None,
        "severity": str | None,
        "channel": str | None,
        "team": str | None,
        "status": str | None,        # "open" | "resolved" | "escalated"

        # Sistema B — Metadatos de cuenta
        "fact_type": str | None,      # "fact" | "episode" | "commitment" | "stakeholder" | "preference"
        "valid_from": str | None,     # ISO 8601
        "valid_to": str | None,       # ISO 8601, None = vigente
        "supersedes": str | None,     # ID del hecho que reemplaza
        "stakeholder": str | None,
        "confidence": float | None,
    }
}
```

### 6.2 Schema de NebulaGraph — Evolución por fases

#### Fase actual (genérico — preservar como fallback)

```ngql
-- Espacio: graphrag
CREATE TAG IF NOT EXISTS entity (name string, type string, description string);
CREATE EDGE IF NOT EXISTS related_to (relation string, weight double);
```

#### Fase 3A — Dominio de soporte

```ngql
-- Espacio: graphrag (mismo espacio, nuevas tags/edges)
CREATE TAG IF NOT EXISTS issue (
    name string, type string, description string,
    product string, version string, severity string,
    status string, channel string, created_at string
);
CREATE TAG IF NOT EXISTS symptom (
    name string, type string, description string
);
CREATE TAG IF NOT EXISTS root_cause (
    name string, type string, description string
);
CREATE TAG IF NOT EXISTS fix (
    name string, type string, description string,
    resolution_type string
);
CREATE TAG IF NOT EXISTS policy (
    name string, type string, description string,
    team string
);

CREATE EDGE IF NOT EXISTS has_symptom (weight double);
CREATE EDGE IF NOT EXISTS caused_by (confidence double);
CREATE EDGE IF NOT EXISTS fixed_by (confidence double);
CREATE EDGE IF NOT EXISTS affects (version string);
CREATE EDGE IF NOT EXISTS escalates_to (team string, condition string);
CREATE EDGE IF NOT EXISTS governed_by (policy string);
```

#### Fase 3B — Dominio de Account Manager

```ngql
-- Nuevas tags/edges con temporalidad
CREATE TAG IF NOT EXISTS account (
    name string, type string, description string,
    industry string, tier string
);
CREATE TAG IF NOT EXISTS stakeholder (
    name string, type string, description string,
    role string, email string, preference string
);
CREATE TAG IF NOT EXISTS commitment (
    name string, type string, description string,
    status string, due_date string
);
CREATE TAG IF NOT EXISTS risk (
    name string, type string, description string,
    severity string, probability string
);
CREATE TAG IF NOT EXISTS opportunity (
    name string, type string, description string,
    stage string, value string
);

CREATE EDGE IF NOT EXISTS has_stakeholder (
    role string, valid_from string, valid_to string
);
CREATE EDGE IF NOT EXISTS has_commitment (
    owner string, status string, due_date string,
    valid_from string, valid_to string
);
CREATE EDGE IF NOT EXISTS has_risk (
    severity string, valid_from string, valid_to string
);
CREATE EDGE IF NOT EXISTS has_opportunity (
    stage string, valid_from string
);
CREATE EDGE IF NOT EXISTS supersedes (
    reason string, superseded_at string
);
```

### 6.3 Modelos Pydantic — Evolución

```python
# app/models/schemas.py — Extensión actual

class CaseMetadata(BaseModel):
    """Metadatos de caso para Sistema A (Soporte)."""
    case_id: str | None = None
    product: str | None = None
    version: str | None = None
    severity: str | None = None
    channel: str | None = None
    team: str | None = None
    status: str | None = None


class FactMetadata(BaseModel):
    """Metadatos de hecho/v Episodio para Sistema B (AM)."""
    account_id: str | None = None
    fact_type: str | None = None       # "fact" | "episode" | "commitment" | "stakeholder" | "preference"
    valid_from: str | None = None
    valid_to: str | None = None
    supersedes: str | None = None
    stakeholder: str | None = None
    confidence: float | None = None


class IngestRequest(BaseModel):
    filename: str
    system: str = "support"            # "support" | "am"
    case_metadata: CaseMetadata | None = None
    fact_metadata: FactMetadata | None = None


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    filters: dict | None = None
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    scope: dict | None = None           # {"system": "support", "product": "...", ...}
    account_id: str | None = None       # Para Sistema B
```

---

## 7. Interfaz de abstracción de retrieval

La interfaz interna de retrieval debe desacoplar la aplicación de los detalles del motor vectorial. Se implementa sobre el `RetrievalEngine` existente.

### 7.1 Firma propuesta

```python
class RetrievalEngine:
    # Existentes (se mantienen)
    def search_dense(self, query, top_k, min_score, filters) -> list[SearchResult]
    def expand_from_graph(self, entity_ids, hops) -> list[SearchResult]
    def fuse_results(self, vector_results, graph_results, max_results) -> tuple
    def log_trace(self, query, phase, candidates, metadata) -> None

    # Nuevas (Fase 2)
    def search_sparse(self, query, top_k, scope, filters) -> list[SearchResult]
    def search_hybrid(self, query, top_k, scope, filters) -> list[SearchResult]
    def search_multivector(self, query, top_k, scope, filters) -> list[SearchResult]
    def rerank(self, candidates, query) -> list[SearchResult]

    # Nuevas (Fase 0)
    def get_supporting_chunks(self, ids) -> list[SearchResult]

    # Scope y namespaces
    # Todos los métodos de búsqueda reciben `scope: dict | None = None`
    # con campos: {"system", "tenant_id", "account_id", "collection", ...}
```

### 7.2 Estructura de resultados extendida

```python
@dataclass
class SearchResult:
    # Existentes
    subject: str
    predicate: str
    object: str
    score: float
    source_doc: str
    chunk_id: str
    subject_id: str
    object_id: str
    subject_type: str = ""
    object_type: str = ""

    # Nuevos
    metadata: dict = field(default_factory=dict)
    retrieval_method: str = ""        # "dense" | "sparse" | "hybrid" | "graph" | "multivector"
    scope: dict = field(default_factory=dict)
```

---

## 8. Integración con Google ADK

### 8.1 Arquitectura de agentes

```
app/
  agents/
    __init__.py
    base.py                    # Agente base con tools compartidas
    support_agent.py           # Agente de soporte (Sistema A)
    account_manager_agent.py   # Agente de AM (Sistema B)
    tools/
      __init__.py
      retrieval_tools.py       # Tools de retrieval (dense, graph, hybrid)
      memory_tools.py          # Tools de memoria episódica y facts
      account_tools.py         # Tools de estado de cuenta (Sistema B)
      case_tools.py            # Tools de caso/ticket (Sistema A)
    prompts/
      support_system.py        # System prompts para soporte
      am_system.py             # System prompts para AM
    evaluation/
      __init__.py
      eval_runner.py           # Runner de evaluación
      metrics.py               # Métricas (relevance, grounding, continuity)
      truth_sets/              # Truth sets labelizados
        support_qa.jsonl
        am_continuity.jsonl
```

### 8.2 Agente de soporte — Tools

| Tool | Descripción | Tipo |
|---|---|---|
| `search_knowledge_base` | Búsqueda dense en corpus de soporte | retrieval |
| `search_by_metadata` | Búsqueda con filtros (producto, versión, severidad) | retrieval |
| `traverse_issue_graph` | Expansión de grafo desde entidades de caso | graph |
| `get_case_history` | Recuperar casos similares | retrieval |
| `escalate_case` | Marcar caso como escalado | action |

### 8.3 Agente de Account Manager — Tools

| Tool | Descripción | Tipo |
|---|---|---|
| `get_account_state` | Recuperar estado vigente de cuenta | memory |
| `search_episodes` | Buscar episodios relevantes por cuenta | retrieval |
| `get_commitments` | Listar compromisos abiertos | memory |
| `get_stakeholder_map` | Mapa de stakeholders y roles | graph |
| `record_fact` | Registrar nuevo hecho o episodio | ingestion |
| `record_commitment` | Registrar compromiso | ingestion |
| `supersede_fact` | Reemplazar hecho anterior por nuevo | memory |

### 8.4 MemoryService y ArtifactService

```
ADK MemoryService
  ├── Memoria de trabajo → Session state (contexto del turno)
  ├── Memoria archival → Qdrant (retrieval bajo demanda)
  └── Estado estructurado → Por sistema:
        Sistema A: estado de caso en session
        Sistema B: estado de cuenta en store dedicado

ADK ArtifactService
  ├── Documentos de soporte (PDFs, tickets)
  └── Reportes de cuenta, contratos, resúmenes de reunión
```

---

## 9. Evaluación

### 9.1 Framework de evaluación

```python
# evals/
#   runner.py          — Ejecuta evaluaciones contra truth sets
#   metrics.py         — Cálculo de relevance@k, MRR, nDCG, grounding
#   truth_sets/
#     support_qa.jsonl  — Preguntas, documentos relevantes, respuestas ideales
#     am_continuity.jsonl — Escenarios de continuidad, hechos esperados
```

### 9.2 Métricas por sistema

| Métrica | Sistema A (Soporte) | Sistema B (AM) |
|---|---|---|
| **Retrieval** | relevance@k, MRR, nDCG | recall correcto de hechos vigentes |
| **Generación** | grounding rate, factuality | continuidad percibida entre sesiones |
| **Operativa** | latencia p50/p95, costo/consulta | latencia p50/p95, costo/conversación |
| **Negocio** | resolución, contención, repeat contact rate | error rate de memoria stale, atribución de stakeholders |

### 9.3 Truth sets

**Soporte (support_qa.jsonl):**
```json
{"question": "...", "relevant_chunks": ["chunk_id_1", ...], "ideal_answer": "...", "product": "...", "version": "..."}
```

**AM (am_continuity.jsonl):**
```json
{"scenario_id": "...", "account_id": "...", "question": "...", "expected_facts": ["fact_1", ...], "expected_commitments": ["comm_1", ...]}
```

---

## 10. Fases de desarrollo

### Fase 0 — Plataforma base compartida

**Objetivo:** Dejar lista la infraestructura mínima transversal para ambos sistemas.

**Duración estimada:** 2-3 semanas

#### 0.1 Integración de Google ADK

| Tarea | Detalle | Archivos |
|---|---|---|
| Instalar ADK | Agregar `google-adk` como dependencia | `pyproject.toml` |
| Crear estructura de agentes | Crear `app/agents/` con base, tools, prompts | `app/agents/` |
| Agente base | Agente genérico con configuración de ADK (Session, state) | `app/agents/base.py` |
| Tool de retrieval básico | Exponer `RetrievalEngine.search_dense()` como tool ADK | `app/agents/tools/retrieval_tools.py` |
| Integrar ADK con FastAPI | Registrar agentes como endpoints adicionales en `app/main.py` | `app/main.py`, `app/api/routes/` |
| Tests de integración ADK | Verificar que el agente base responde con retrieval | `tests/test_agents.py` |

#### 0.2 Extender RetrievalEngine

| Tarea | Detalle | Archivos |
|---|---|---|
| Agregar `scope` a métodos | Todos los métodos de búsqueda reciben `scope: dict \| None` con `system`, `tenant_id`, `account_id` | `app/core/retrieval.py` |
| Stubs para sparse/hybrid | Agregar `search_sparse()` y `search_hybrid()` con NotImplementedError o fallback a dense | `app/core/retrieval.py` |
| `get_supporting_chunks()` | Recuperar chunks completos por ID | `app/core/retrieval.py` |
| Namespaces en Qdrant | Agregar payload fields `system`, `tenant_id`, `account_id` a todos los puntos nuevos. Actualizar `ensure_collection_exists()` para crear índices | `app/core/vectorstore.py` |
| Tests | Tests unitarios para scope, namespaces, nuevos métodos | `tests/test_vectorstore.py`, `tests/test_retrieval.py` |

#### 0.3 Contratos de identidad y provenance

| Tarea | Detalle | Archivos |
|---|---|---|
| Extender `IngestRequest` | Agregar campos `system`, `case_metadata`, `fact_metadata` | `app/models/schemas.py` |
| Extender `QueryRequest` | Agregar campos `scope`, `account_id` | `app/models/schemas.py` |
| Extender payload de Qdrant | Agregar campos de namespace y dominio al ingestion pipeline | `app/pipelines/ingestion.py` |
| Actualizar API routes | Reflejar nuevos campos en endpoints | `app/api/routes/ingest.py`, `app/api/routes/query.py` |
| Tests | Tests de validación de nuevos esquemas | `tests/test_schemas.py` |

#### 0.4 Framework de evaluación

| Tarea | Detalle | Archivos |
|---|---|---|
| Crear directorio `evals/` | Estructura para truth sets y scripts | `evals/` |
| Script de baseline evaluation | Medir relevance@k del retrieval actual | `evals/runner.py` |
| Truth set inicial de soporte | 20-50 pares pregunta-documento labelizados | `evals/truth_sets/support_qa.jsonl` |
| Métricas de retrieval | relevance@k, MRR básico | `evals/metrics.py` |
| CI integration | Ejecutar evals en el pipeline de test | `Makefile`, `pyproject.toml` |

#### 0.5 Pipeline de consolidación compartido

| Tarea | Detalle | Archivos |
|---|---|---|
| Crear `consolidation.py` | Pipeline de 7 pasos: capturar → extraer → clasificar → consolidar → deduplicar → supersession → provenance | `app/pipelines/consolidation.py` |
| Taxonomía de memoria | Clasificación: estado estructurado, episódico, semántico documental, procedural | `app/models/schemas.py` |
| `MemoryWriter` | Escritura de facts/episodes a Qdrant con metadatos de tipo, vigencia y provenance | `app/pipelines/memory_writer.py` |
| Deduplicación | Contra memoria existente antes de insertar | `app/pipelines/consolidation.py` |
| Supersession | Marcar hechos anteriores como reemplazados | `app/pipelines/consolidation.py` |
| Tests | Unit tests del pipeline de consolidación con mocks | `tests/test_consolidation.py` |

#### 0.5 Logging y observabilidad mejorada

| Tarea | Detalle | Archivos |
|---|---|---|
| Persistir retrieval traces | Guardar `RetrievalTrace` en archivo JSONL estructurado | `app/core/retrieval.py` |
| Correlación end-to-end | Agregar `trace_id` y `session_id` a todos los logs de pipeline | `app/pipelines/query.py`, `app/pipelines/ingestion.py` |
| Endpoint de traces | GET `/api/v1/traces?query=...` para consultar traces de retrieval | `app/api/routes/` |

#### Criterios de aceptación Fase 0

- [ ] `make run` levanta Docker + API + ADK agents sin errores
- [ ] Health check reporta Qdrant, NebulaGraph, LLM y ADK como servicios
- [ ] `RetrievalEngine.search_dense()` acepta `scope` y filtra por `system` y `account_id`
- [ ] Ingestión con `system="support"` y `system="am"` almacena puntos en Qdrant con namespace correcto
- [ ] Truth set de soporte con 20+ pares pregunta-documento
- [ ] Script de evaluación ejecuta y reporta relevance@k
- [ ] Retrieval traces se persisten en JSONL

---

### Fase 1A — MVP de Soporte Virtual

**Objetivo:** Agente de soporte que responde preguntas con grounding y trazabilidad.

**Duración estimada:** 3-4 semanas

#### 1A.1 Agente de soporte en ADK

| Tarea | Detalle | Archivos |
|---|---|---|
| Definir agente de soporte | Custom Agent con tools de retrieval, system prompt específico | `app/agents/support_agent.py` |
| Tool `search_knowledge_base` | Dense retrieval con filtros de dominio | `app/agents/tools/retrieval_tools.py` |
| Tool `search_by_metadata` | Búsqueda con filtros (producto, versión, severidad) | `app/agents/tools/retrieval_tools.py` |
| Tool `traverse_issue_graph` | Expansión de grafo desde entidades de caso | `app/agents/tools/retrieval_tools.py` |
| System prompt de soporte | Prompt grounded con instrucciones de trazabilidad y manejo de incertidumbre | `app/agents/prompts/support_system.py` |
| Endpoint ADK de soporte | `/api/v1/agents/support/query` y `/api/v1/agents/support/query/stream` | `app/api/routes/` |

#### 1A.2 Ingesta orientada a caso

| Tarea | Detalle | Archivos |
|---|---|---|
| Modelo `CaseMetadata` | Campos: `case_id`, `product`, `version`, `severity`, `channel`, `team`, `status` | `app/models/schemas.py` |
| Prompt de extracción para soporte | Prompt especializado para Issues, Symptoms, Root Causes, Fixes, Policies | `app/prompts/extraction_support.py` |
| Extender ingestion pipeline | Rama de ingesta con `system="support"` y `case_metadata` | `app/pipelines/ingestion.py` |
| Filtros de dominio en retrieval | Filtrar por `product`, `version`, `severity`, `status` en Qdrant | `app/core/retrieval.py` |
| UI: campos de caso en Upload | Exponer `case_metadata` en la página de Upload de Streamlit | `ui/pages/1_Upload.py` |

#### 1A.3 Respuesta grounded

| Tarea | Detalle | Archivos |
|---|---|---|
| Prompt de QA grounded | Instrucciones de citation, manejo de incertidumbre, formato estructurado | `app/prompts/qa_support.py` |
| Respuesta con evidencias | Formato de respuesta: resumen, pasos sugeridos, evidencias, incertidumbre | `app/models/schemas.py` |
| UI: vista de respuesta grounded | Mostrar evidencias con links a chunks, confidence expandido | `ui/pages/3_Query.py` |

#### 1A.4 Evaluación baseline del MVP

| Tarea | Detalle | Archivos |
|---|---|---|
| Extender truth set | 50-100 pares pregunta-documento con ideal answers | `evals/truth_sets/support_qa.jsonl` |
| Métricas de generación | Grounding rate (respuesta sostenida por evidencia), faithfulness | `evals/metrics.py` |
| Reporte baseline | Documento con baseline de retrieval y generación | `evals/reports/baseline_support.md` |

#### Criterios de aceptación Fase 1A

- [ ] Agente de soporte responde preguntas con fuentes trazables
- [ ] Ingesta con metadatos de caso se almacena correctamente en Qdrant
- [ ] Filtros por producto, versión, severidad operan en queries
- [ ] Respuestas incluyen evidencias y nivel de incertidumbre
- [ ] relevance@5 > 0.6 en truth set de soporte
- [ ] Grounding rate > 0.7 (respuestas sostenidas por contexto recuperado)

---

### Fase 1B — MVP de Account Manager

**Objetivo:** Agente de AM que mantiene continuidad relacional y operativa.

**Duración estimada:** 3-4 semanas

#### 1B.1 Modelo de hechos y episodios

| Tarea | Detalle | Archivos |
|---|---|---|
| Modelo `Fact` | Pydantic con `account_id`, `fact_type`, `key`, `value`, `valid_from`, `valid_to`, `supersedes`, `source`, `confidence` | `app/models/schemas.py` |
| Modelo `Episode` | Pydantic con `account_id`, `date`, `type`, `summary`, `participants`, `outcomes`, `commitments` | `app/models/schemas.py` |
| Modelo `AccountState` | Pydantic con campos estructurados: stakeholders, objectives, risks, commitments, blockers | `app/models/schemas.py` |
| Persistencia de Facts y Episodes | Qdrant collection `account_knowledge` (o namespace dentro de `triplets`) | `app/core/vectorstore.py` |
| Tests de modelos | Validación, serialización, deduplicación | `tests/test_schemas.py` |

#### 1B.2 Store estructurado de cuenta

| Tarea | Detalle | Archivos |
|---|---|---|
| `AccountStore` | Clase que gestiona estado vigente de cuenta: `get_state()`, `update_state()`, `add_fact()`, `supersede_fact()` | `app/core/account_store.py` |
| Store por cuenta en Qdrant | Queries con `account_id` + `valid_to=None` para hechos vigentes | `app/core/account_store.py` |
| Artifacts por cuenta | Guardar documentos asociados a cuenta (contratos, resúmenes) | Integrar con ADK ArtifactService |
| Tests | Unit tests del AccountStore con mocks de Qdrant | `tests/test_account_store.py` |

#### 1B.3 Agente de Account Manager en ADK

| Tarea | Detalle | Archivos |
|---|---|---|
| Definir agente de AM | Custom Agent con session state, carga de cuenta, memoria episódica | `app/agents/account_manager_agent.py` |
| Tool `get_account_state` | Recuperar estado vigente de cuenta | `app/agents/tools/account_tools.py` |
| Tool `search_episodes` | Buscar episodios relevantes por cuenta | `app/agents/tools/memory_tools.py` |
| Tool `get_commitments` | Listar compromisos abiertos | `app/agents/tools/account_tools.py` |
| Tool `get_stakeholder_map` | Mapa de stakeholders y roles (de grafo) | `app/agents/tools/account_tools.py` |
| Tool `record_fact` | Registrar nuevo hecho o episodio | `app/agents/tools/memory_tools.py` |
| Tool `supersede_fact` | Reemplazar hecho anterior por nuevo | `app/agents/tools/memory_tools.py` |
| System prompt de AM | Instrucciones de continuidad, manejo de hechos vigentes vs. pasados | `app/agents/prompts/am_system.py` |
| Endpoint ADK de AM | `/api/v1/agents/am/query`, `/api/v1/agents/am/state/{account_id}` | `app/api/routes/` |

#### 1B.4 Prompt de extracción para AM

| Tarea | Detalle | Archivos |
|---|---|---|
| Prompt de extracción de AM | Detectar facts, episodes, commitments, stakeholders, preferences en texto | `app/prompts/extraction_am.py` |
| Clasificación de hechos | LLM clasifica: fact vs. episode vs. commitment vs. preference | `app/pipelines/ingestion.py` |
| Ingesta con `system="am"` | Rama de ingesta con `fact_metadata` y clasificación | `app/pipelines/ingestion.py` |

#### 1B.5 Evaluación de continuidad

| Tarea | Detalle | Archivos |
|---|---|---|
| Truth set de AM | Escenarios de continuidad: sesión 1 establece hechos, sesión 2 los recupera | `evals/truth_sets/am_continuity.jsonl` |
| Métricas de continuidad | Recall de hechos vigentes, error rate de memoria stale, atribución de stakeholders | `evals/metrics.py` |
| Reporte baseline de AM | Documento con baseline de continuidad | `evals/reports/baseline_am.md` |

#### Criterios de aceptación Fase 1B

- [ ] Agente de AM carga estado de cuenta al inicio de sesión
- [ ] Facts se almacenan con `account_id` y `valid_from`/`valid_to`
- [ ] Supersession de hechos funciona (hecho nuevo reemplaza viejo, historial preservado)
- [ ] Recuperación selectiva: `valid_to=None` devuelve solo hechos vigentes
- [ ] Continuidad entre sesiones demostrable (sesión 2 recuerda hechos de sesión 1)
- [ ] Recall de compromisos vigentes > 0.7 en truth set

---

### Fase 2 — Hardening de Retrieval

**Objetivo:** Mejorar calidad de retrieval antes de añadir complejidad de grafo.

**Duración estimada:** 2-3 semanas

| Tarea | Detalle | Archivos |
|---|---|---|
| Sparse retrieval (BM25) | Activar sparse vectors en Qdrant, implementar `search_sparse()` | `app/core/retrieval.py`, `app/core/vectorstore.py` |
| Hybrid retrieval | Fusión RRF server-side en Qdrant, implementar `search_hybrid()` | `app/core/retrieval.py` |
| Reranking | Implementar `rerank()` — modelo de rerank o LLM-based | `app/core/retrieval.py` |
| Deduplicación mejorada | Fusión por score combinado (no solo key dedup) | `app/core/retrieval.py` |
| Tuning de chunking | Experimentar con `CHUNK_SIZE`, `CHUNK_OVERLAP`, chunking semántico | `app/pipelines/ingestion.py` |
| Evaluación continua | Scripts automáticos, métricas de retrieval y generación, comparación A/B | `evals/` |
| Logging mejorado | Persistir traces de retrieval completos, métricas de latencia | `app/core/retrieval.py` |

#### Criterios de aceptación Fase 2

- [ ] `search_sparse()` y `search_hybrid()` operativos y testeados
- [ ] Reranking mejora relevance@5 en al menos 10% sobre baseline
- [ ] Evaluación automática ejecuta contra truth set y reporta métricas
- [ ] Latencia p95 de retrieval < 500ms
- [ ] Traces de retrieval completos disponibles para debugging

---

### Fase 3A — Grafo de dominio para Soporte

**Objetivo:** Capturar relaciones útiles entre incidentes, causas, fixes y entidades del dominio.

**Duración estimada:** 2-3 semanas

| Tarea | Detalle | Archivos |
|---|---|---|
| Schema de soporte en NebulaGraph | Tags: `issue`, `symptom`, `root_cause`, `fix`, `policy`. Edges: `has_symptom`, `caused_by`, `fixed_by`, `affects`, `escalates_to` | `app/models/graph_schema.py`, `scripts/init_nebula.py` |
| Prompt de extracción estructurada | Extraer entidades de dominio (Issue, Symptom, RootCause, Fix) con tipos específicos | `app/prompts/extraction_support.py` |
| Ingesta con schema de dominio | Pipeline bifurcado: genérico (actual) + dominio específico | `app/pipelines/ingestion.py` |
| Consultas multi-hop | Traversal con filtros por tipo de relación para troubleshooting | `app/core/graph.py`, `app/core/retrieval.py` |
| Graph-assisted retrieval | Consultas de grafo para expandir contexto relevante antes de generar | `app/pipelines/query.py` |
| UI: vista de troubleshooting | Visualización de Issue→Symptom→RootCause→Fix | `ui/pages/` |

#### Criterios de aceptación Fase 3A

- [ ] NebulaGraph tiene tags y edges de dominio de soporte operativos
- [ ] Extracción de entidades de dominio funciona (Issue, Symptom, RootCause, Fix)
- [ ] Consultas multi-hop con filtros por tipo de relación funcionan
- [ ] Graph-assisted retrieval mejora respuestas en al menos 15% de casos de troubleshooting

---

### Fase 3B — Grafo temporal para Account Manager

**Objetivo:** Mejorar razonamiento relacional e histórico.

**Duración estimada:** 2-3 semanas

| Tarea | Detalle | Archivos |
|---|---|---|
| Schema de AM en NebulaGraph | Tags: `account`, `stakeholder`, `commitment`, `risk`, `opportunity`. Edges con `valid_from`, `valid_to` | `app/models/graph_schema.py`, `scripts/init_nebula.py` |
| Vigencia temporal | Queries que filtran por `valid_to = NULL` (hechos vigentes) y por rango temporal | `app/core/graph.py` |
| Supersession estructurada | Marcar edges como reemplazados, preservar historial | `app/core/account_store.py` |
| Consultas sobre cambios en el tiempo | "Qué cambió desde la última renovación?" | `app/core/graph.py`, `app/core/retrieval.py` |
| Tool de stakeholder map mejorado | Usa el grafo para mapear relaciones entre actores | `app/agents/tools/account_tools.py` |

#### Criterios de aceptación Fase 3B

- [ ] NebulaGraph modela stakeholders, compromisos, riesgos con vigencia temporal
- [ ] Queries de hechos vigentes (`valid_to=NULL`) funcionan correctamente
- [ ] Supersection: un hecho nuevo marca el viejo como `valid_to=ahora`
- [ ] El agente de AM responde preguntas temporales ("qué cambió desde X")

---

### Fase 4 — Carriles experimentales

**Objetivo:** Probar mejoras sin comprometer estabilidad.

**Duración estimada:** 2-4 semanas

| Tarea | Detalle |
|---|---|
| Lane multi-vector local | Qdrant con multivectors y modelos tipo ColBERT / late interaction |
| Lane Wholembed v3 managed | Sidecar managed en cohorte limitada (5% tráfico) |
| Shadow mode | Ejecutar retrieval experimental en paralelo, registrar métricas |
| Sticky cohorts | Hash determinista para asignar cuentas a variantes |
| Métricas comparativas | relevance@k, latencia, costo por consulta, comparativa contra baseline |
| POC de Graphiti | Solo para AM, si hay señal de necesidad (alta tasa de stale facts, mala supersession) |

#### Criterios de aceptación Fase 4

- [ ] Al menos un lane experimental operativo (multi-vector local o Wholembed)
- [ ] Shadow mode registra métricas sin afectar usuarios
- [ ] Decisión data-driven sobre adopción de lane experimental

---

### Fase 5 — Managed y escalado

**Objetivo:** Elegir forma de operación de largo plazo.

**Duración estimada:** 2-3 semanas

| Tarea | Detalle |
|---|---|
| Decisión self-hosted vs Qdrant Cloud | Basada en métricas de operación, costo y SLA |
| Hardening de seguridad | TLS, autenticación, autorización multi-tenant |
| Backups y DR | Estrategia de backup para Qdrant y NebulaGraph |
| Optimización de costos | Monitor y alertas de uso de LLM, embeddings, almacenamiento |
| Operación multi-tenant | Isolation por tenant en Qdrant y NebulaGraph |

---

## 11. Estructura de proyecto — Estado objetivo

```
graphrag-poc/
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app (existente, extendida)
│   ├── config.py                    # Settings (existente, extendido)
│   ├── agents/                      # NUEVO — Google ADK agents
│   │   ├── __init__.py
│   │   ├── base.py                  # Agente base con tools compartidas
│   │   ├── support_agent.py         # Agente de soporte (Sistema A)
│   │   ├── account_manager_agent.py # Agente de AM (Sistema B)
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── retrieval_tools.py   # Tools de retrieval
│   │   │   ├── memory_tools.py       # Tools de memoria (facts, episodes)
│   │   │   ├── account_tools.py      # Tools de estado de cuenta
│   │   │   └── case_tools.py         # Tools de caso/ticket
│   │   └── prompts/
│   │       ├── __init__.py
│   │       ├── support_system.py    # System prompt soporte
│   │       └── am_system.py         # System prompt AM
│   ├── api/
│   │   ├── __init__.py
│   │   ├── exceptions.py             # (existente)
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── health.py             # (existente)
│   │       ├── ingest.py             # (existente, extendido con system y metadata)
│   │       ├── query.py              # (existente, extendido con scope)
│   │       ├── documents.py          # (existente)
│   │       ├── graph.py              # (existente)
│   │       ├── agents.py             # NUEVO — ADK agent endpoints
│   │       ├── memory.py             # NUEVO — Memory endpoints
│   │       ├── account.py            # NUEVO — Account state endpoints
│   │       └── traces.py             # NUEVO — Retrieval trace endpoints
│   ├── core/
│   │   ├── __init__.py
│   │   ├── llm.py                    # (existente)
│   │   ├── embeddings.py             # (existente)
│   │   ├── graph.py                  # (existente, extender para schemas de dominio)
│   │   ├── vectorstore.py            # (existente, extender con namespaces)
│   │   ├── retrieval.py              # (existente, extender con scope, sparse, hybrid)
│   │   └── account_store.py          # NUEVO — Store estructurado de cuenta
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py               # (existente, extender con CaseMetadata, Fact, Episode, AccountState)
│   │   └── graph_schema.py          # (existente, extender con schemas de dominio)
│   ├── pipelines/
│   │   ├── __init__.py
│   │   ├── ingestion.py              # (existente, extender con system routing)
│   │   ├── loaders.py                # (existente)
│   │   ├── query.py                  # (existente, refactorizar para usar Agent tools)
│   │   ├── consolidation.py          # NUEVO — Pipeline de consolidación compartido
│   │   └── memory_writer.py          # NUEVO — Escritura de facts/episodes a stores
│   └── prompts/
│       ├── __init__.py
│       ├── extraction.py             # (existente, genérico)
│       ├── extraction_support.py     # NUEVO — Soporte
│       ├── extraction_am.py          # NUEVO — Account Manager
│       ├── qa.py                     # (existente, genérico)
│       ├── qa_support.py             # NUEVO — Grounded QA para soporte
│       └── qa_am.py                  # NUEVO — Continuity QA para AM
├── evals/
│   ├── __init__.py
│   ├── runner.py                     # Ejecuta evaluaciones contra truth sets
│   ├── metrics.py                    # relevance@k, MRR, nDCG, grounding, continuity
│   └── truth_sets/
│       ├── support_qa.jsonl          # Preguntas, chunks relevantes, respuestas ideales
│       └── am_continuity.jsonl        # Escenarios de continuidad
├── scripts/
│   ├── init_nebula.py                # (existente, extender con schemas de dominio)
│   └── seed.py                        # (existente)
├── ui/                               # (existente, extendido)
│   ├── app.py
│   ├── components/
│   │   ├── api_client.py             # (existente, extender con nuevos endpoints)
│   │   ├── sidebar.py
│   │   └── graph_renderer.py
│   └── pages/
│       ├── 1_Upload.py               # (existente, extender con case_metadata)
│       ├── 2_Graph.py
│       ├── 3_Query.py                # (existente, extender con scope/filtros)
│       ├── 4_Documents.py
│       ├── 5_Account.py              # NUEVO — Vista de estado de cuenta
│       └── 6_Evaluation.py          # NUEVO — Vista de métricas
├── tests/                            # (existente, extender)
│   ├── test_core.py
│   ├── test_vectorstore.py
│   ├── test_ingestion.py
│   ├── test_query.py
│   ├── test_schemas.py
│   ├── test_api.py
│   ├── test_api_client.py
│   ├── test_loaders.py
│   ├── test_agents.py               # NUEVO
│   ├── test_account_store.py        # NUEVO
│   ├── test_consolidation.py        # NUEVO — Pipeline de consolidación
│   ├── test_memory_writer.py        # NUEVO — Escritura de facts/episodes
│   └── test_evals.py                # NUEVO
├── config/
│   └── nebula/                        # (existente)
├── docker-compose.yml                 # (existente, sin cambios mayores)
├── pyproject.toml                    # Extender con google-adk, evals
├── Makefile                           # Extender con targets de evals
├── AGENTS.md                         # (existente, actualizar)
└── docs/
    ├── ARCHITECTURE.md               # (existente, actualizar)
    ├── PRD.md                         # (existente, PoC original)
    ├── PRD-STREAMLIT.md              # (existente, Streamlit)
    └── PRD-MEMORY-SYSTEMS.md         # ESTE DOCUMENTO
```

---

## 12. Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| ADK no cubre necesidades de memoria longitudinal | Media | Alto | Diseñar MemoryService custom desde Fase 0, desacoplar de ADK |
| NebulaGraph schemas de dominio son muy rígidos | Media | Medio | Mantener `entity` + `related_to` como fallback, schemas de dominio como capa adicional |
| Retrieval dense no suficiente para soporte | Baja | Medio | Fase 2 (sparse/hybrid) como primer hardening, antes de grafo de dominio |
| Extracción LLM produce triplets ruidosos | Alta | Medio | Prompts especializados por dominio, evaluación continua, human-in-the-loop para Fase 1A |
| Costo de LLM en producción | Media | Medio | Monitorear uso, optimizar prompts, cachear respuestas frecuentes |
| Modelo de datos compartido vs. separado | Pendiente | Alto | Decisión pendiente — afecta Qdrant collections y NebulaGraph spaces |

---

## 13. Dependencias entre fases

```
Fase 0 ──────┬─── Fase 1A ──── Fase 2 ──── Fase 3A
             │                                  │
             └─── Fase 1B ──── Fase 2 ──── Fase 3B
                                            │
                                            └─── Fase 4 ──── Fase 5
```

- **Fase 0** es prerrequisito de todo.
- **Fase 1A y 1B** pueden ir en paralelo tras Fase 0, reutilizando infraestructura transversal.
- **Fase 2** es prerrequisito de **Fase 3A y 3B** (mejor retrieval antes de grafo complejo).
- **Fase 4 y 5** son iterativas y pueden solaparse con Fase 3.

---

## 14. Decisión pendiente: Modelo de datos compartido vs. separado

| Opción | Ventajas | Desventajas |
|---|---|---|
| **Compartido con namespaces** | Menos colecciones, menos mantenimiento, retrieval cross-system posible | Aislamiento requiere filtros estrictos, riesgo de contaminación |
| **Separado por sistema** | Aislamiento natural, schemas独立, evolución独立 | Más colecciones, más mantenimiento, no permite retrieval cross-system fácil |
| **Híbrido** (Qdrant compartido con namespaces, NebulaGraph separado) | Balance entre simplicidad y aislamiento | Complejidad intermedia, requiere consistencia de namespaces en dos sistemas |

**Recomendación tentativa:** Híbrido — Qdrant compartido con `system` field como namespace, NebulaGraph con tags/edges separados por dominio dentro del mismo space. Revisar tras Fase 0.

---

## 15. No-go para MVP

Las siguientes capacidades **no** entran en la ruta crítica del MVP y se consideran para fases posteriores. Cada no-go está acompañado del veredicto del documento original y la condición para reconsiderar.

| Capacidad | Veredicto | Condición para reconsiderar |
|---|---|---|
| **Graphiti como dependencia** | No entra. Conceptualmente valioso pero desalineado con NebulaGraph (solo soporta Neo4j, FalkorDB, Neptune, Kuzu). Introduciría un segundo backend de grafo. | POC experimental solo para Sistema B si aparecen síntomas: alta tasa de stale facts, errores de continuidad, mala supersession |
| **Wholembed v3 como reemplazo del baseline** | No como base del MVP. Entra como lane experimental. El baseline dense/hybrid es más simple de operar y evaluar. | Cuando el Lane A (Qdrant native) tenga baseline fuerte y se pueda comparar contra Lane B/C con datos propios |
| **GraphRAG completo (extracción global, community detection, reportes jerárquicos)** | No conviene meter de entrada. Solo cuando exista un corpus amplio y necesidad clara de responder preguntas transversales. | Fase 3A o posterior, si la evidencia de retorno es clara |
| **Milvus / Zilliz Cloud** | Opción válida para futuro, no para MVP. La capa de abstracción reduce el costo de migración. | Fase 5, si hay razones estratégicas ecosistema o rendimiento |
| **Multi-tenancy completo con aislamiento por tenant** | Escalado posterior. El MVP funciona con namespaces por campo. | Fase 5 |
| **RAG multimodal (imágenes, audio)** | Fuera de alcance. | Evaluación futura |
| **Agentes autónomos con planificación multi-paso** | Fuera de alcance del MVP. Los agentes son reactivos (tool-calling), no autónomos con planificación. | Evaluación futura |

### Decisión sobre Graphiti (detalle adicional del documento original)

Graphiti es conceptualmente cercano al Sistema B (memoria temporal para agentes, actualizaciones incrementales, episodios, provenance). Sin embargo:

- La documentación lista Neo4j como backend principal, no NebulaGraph
- No hay soporte oficial documentado para NebulaGraph
- Introducirlo hoy implicaría: (a) añadir un segundo backend de grafo, (b) invertir en un adapter no trivial, o (c) aceptar complejidad operativa adicional

**Recomendación:** No usar como base del MVP. Considerar como POC comparativo en Fase 4 solo para el Sistema B, si aparecen síntomas concretos de necesidad (alta tasa de stale facts, errores frecuentes de continuidad, mala gestión de supersession).

---

## 16. Métricas de seguimiento

### 16.1 Métricas de Soporte (Sistema A)

| Métrica | Definición | Fase 1A (baseline) | Fase 2 (target) | Fase 3A (target) |
|---|---|---|---|---|
| **relevance@5** | Proporción de resultados relevantes en top-5 | > 0.6 | > 0.7 | > 0.75 |
| **MRR** | Reciprocal rank del primer resultado relevante | baseline | +10% vs baseline | +15% vs baseline |
| **nDCG@10** | Normalized discounted cumulative gain | baseline | medir | +10% vs baseline |
| **Grounding rate** | Proporción de respuestas sostenidas por evidencia recuperada | > 0.7 | > 0.8 | > 0.85 |
| **Resolución / contención** | Proporción de consultas resueltas sin escalar | medir | medir | > 0.5 |
| **Repeat contact rate** | Proporción de usuarios que vuelven a consultar lo mismo | medir | medir | reducir |
| **Latencia p50** | Mediana de tiempo de respuesta | < 500ms | < 300ms | < 300ms |
| **Latencia p95** | Percentil 95 de tiempo de respuesta | < 2s | < 1s | < 1s |
| **Costo por consulta** | Costo de LLM + embeddings por query | baseline | -10% | -15% |
| **Costo por caso resuelto** | Costo total para resolver un caso end-to-end | baseline | medir | reducir |

### 16.2 Métricas de Account Manager (Sistema B)

| Métrica | Definición | Fase 1B (baseline) | Fase 2 (target) | Fase 3B (target) |
|---|---|---|---|---|
| **Recall de compromisos vigentes** | Proporción de compromisos abiertos correctamente recuperados | > 0.7 | > 0.8 | > 0.85 |
| **Error rate de memoria stale** | Proporción de hechos reportados como vigentes que ya no lo son | baseline | reducir 20% | < 10% |
| **Atribución correcta de stakeholders** | Proporción de stakeholders correctamente identificados | > 0.7 | > 0.8 | > 0.85 |
| **Continuidad entre sesiones** | Proporción de hechos de sesión previa correctamente recordados | demo | > 0.7 | > 0.8 |
| **Latencia p50** | Mediana de tiempo de respuesta | < 500ms | < 300ms | < 300ms |
| **Latencia p95** | Percentil 95 de tiempo de respuesta | < 2s | < 1s | < 1s |
| **Costo por conversación útil** | Costo de LLM + retrieval por conversación con outcome | baseline | medir | reducir |

### 16.3 Métricas de retrieval (compartidas)

| Métrica | Definición | Cómo se mide |
|---|---|---|
| **relevance@k** | Proporción de resultados relevantes en top-k | Truth set labelizado, comparación automática |
| **MRR** | Mean Reciprocal Rank | Truth set, posición del primer relevante |
| **nDCG@10** | Normalized Discounted Cumulative Gain | Truth set con graded relevance |
| **Grounding rate** | Respuestas sostenidas por contexto recuperado | Evaluación humana o LLM-as-judge |
| **Recall@k** | Proporción de relevantes recuperados del total | Truth set, comparación exhaustiva |

---

## 17. Metodología de A/B testing

### 17.1 Lanes de retrieval

| Lane | Tipo | Tecnología | Fase |
|---|---|---|---|
| **A (Control)** | Dense retrieval → dense+sparse → hybrid | Qdrant native | 0-2 |
| **B (Experimento local)** | Multi-vector con late interaction (ColBERT) | Qdrant multivectors | 4 |
| **C (Experimento managed)** | Wholembed v3 como sidecar | Mixedbread API | 4 |

### 17.2 Secuencia de testing

1. **Shadow mode**: El usuario sigue viendo Lane A, pero Lane B/C se ejecuta en paralelo y se registran métricas. Sin impacto en experiencia.
2. **Sticky cohorts**: Cada cuenta o tenant queda asignada de forma estable a una variante mediante hash determinista. A/B real.
3. **Incremento gradual**: 5% → 10% → 25% → 50% → 100%, según criterios de calidad y operación.
4. **Rollback trivial**: Desactivar un lane sin tocar la lógica central de la aplicación. La abstracción de retrieval lo permite.

### 17.3 Criterios de promoción y rollback

| Criterio | Promocionar a producción | Rollback |
|---|---|---|
| relevance@5 | > baseline + 5% | < baseline - 2% |
| Latencia p95 | < baseline + 20% | > baseline + 50% |
| Costo por query | < baseline + 10% | > baseline + 30% |
| Grounding rate | > baseline | < baseline - 5% |

---

## 18. Ruta de evolución de infraestructura

### 18.1 Qdrant

| Etapa | Configuración | Cuándo |
|---|---|---|
| **Local self-hosted** | Qdrant Docker, disco local | Fase 0-2 (MVPs + hardening) |
| **Qdrant Cloud** | Managed, misma API, sin ops | Fase 5 si se busca continuidad operativa sin ops |
| **Milvus / Zilliz Cloud** | Solo si hay razones estratégicas, ecosistema o rendimiento | Evaluación en Fase 5 |

La capa de abstracción de retrieval (`RetrievalEngine`) reduce el costo de migración entre estos backends. No se migra hasta que la evidencia lo justifique.

### 18.2 NebulaGraph

| Etapa | Configuración | Cuándo |
|---|---|---|
| **Docker 3-node cluster** | Actual: metad + storaged + graphd | Fase 0-2 |
| **Schema de dominio** | Agregar tags/edges de soporte y AM | Fase 3A/3B |
| **Optimización de queries** | Índices, tuning de particiones |Según carga |
| **Managed** | Solo si operativamente necesario | Evaluación futura |