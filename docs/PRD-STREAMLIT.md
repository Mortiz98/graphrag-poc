# PRD: Streamlit UI + Graph Visualization for GraphRAG PoC

## 1. Summary

Add an interactive Streamlit frontend that connects to the existing FastAPI backend, allowing users to ingest documents, visualize the knowledge graph in real time, and query the system — all from a single `make run` command.

## 2. Objectives

| # | Objective | Success Criteria |
|---|-----------|-------------------|
| U1 | One-command startup | `make run` launches Docker + API + Streamlit |
| U2 | Document upload UI | Drag-and-drop file uploader with ingestion progress feedback |
| U3 | Interactive graph visualization | Visual network of entities and relations with zoom, filter, hover details |
| U4 | Query chat interface | Ask questions, see answers with sources and confidence |
| U5 | Document management | List, inspect, and delete ingested documents |
| U6 | Real-time graph stats | Live counters for entities, edges, and documents |

## 3. Tech Stack

| Component | Technology | Why |
|-----------|------------|-----|
| UI Framework | **Streamlit** | Rapid prototyping, no frontend build, Python-native |
| Graph Visualization | **Streamlit Cytoscape** (`streamlit-cytoscapejs`) | Interactive, zoomable, styled graph — no HTML exports, stays inside Streamlit natively |
| Startup Orchestrator | **Makefile + shell** | Simple, no extra deps, `make run` does everything |
| Backend API | **FastAPI** (existing) | No changes needed |

### Why not pyvis?

Pyvis generates standalone HTML files. You'd need to embed them via `st.components.v1.html()`, losing interactivity and integration with Streamlit's state. Cytoscape.js renders natively inside Streamlit, supports click events, styling, and layout config — all without leaving the app.

## 4. Architecture

```
make run
  ├── docker compose up -d          (Qdrant + NebulaGraph)
  ├── uv run uvicorn app.main:app   (FastAPI :8000)
  └── uv run streamlit run ui/app.py (Streamlit :8501)

┌──────────────────────────────────┐
│         Streamlit (:8501)         │
│  ┌─────────┬─────────┬────────┐  │
│  │ Upload  │  Graph   │  Chat  │  │
│  │  Docs   │   View   │   &    │  │
│  │         │         │ Query  │  │
│  └────┬────┴────┬────┴───┬────┘  │
│       │         │        │       │
│       ▼         ▼        ▼       │
│  ┌─────────────────────────────┐ │
│  │    httpx (REST client)      │ │
│  └──────────────┬──────────────┘ │
└─────────────────┼────────────────┘
                  │ HTTP :8000
                  ▼
         ┌─────────────────┐
         │   FastAPI API    │
         └────────┬────────┘
                  │
     ┌────────────┼────────────┐
     ▼            ▼            ▼
  Qdrant     NebulaGraph   OpenRouter
```

## 5. Streamlit Pages

### 5.1 — Dashboard / Home (`/`)

**Purpose:** System overview at a glance.

- Service health status (green/red indicators for Qdrant, NebulaGraph, LLM)
- Live counters: total documents, entities, edges
- Recent ingestion history (last 5 documents with status)

### 5.2 — Upload Documents (`/Upload`)

**Purpose:** Ingest new documents into the system.

- `st.file_uploader` accepting `.pdf`, `.txt`, `.md` (multiple files)
- On upload: call `POST /api/v1/ingest` for each file
- Progress bar or spinner per file
- Result cards showing: filename, chunks, triplets extracted, status
- "Seed sample data" button — calls `scripts/seed.py` logic via API

### 5.3 — Graph Explorer (`/Graph`)

**Purpose:** Interactive visualization of the knowledge graph.

**Core view:**
- Cytoscape graph with entities as nodes, `related_to` edges as links
- Node color by entity type (Technology=blue, Person=green, Organization=orange, Concept=purple, etc.)
- Edge labels showing relation (`predicate`)
- Node size proportional to degree (more connections = bigger)
- Click on node → sidebar with entity details (name, type, connections list)

**Filters:**
- Filter by source document (multi-select)
- Filter by entity type (multi-select)
- Filter by relation type (multi-select)
- Search box to highlight/find specific entities
- Degree slider: "show only entities with ≥ N connections"
- "Hops from entity" — select a seed entity, show N-hop neighborhood

**Layout options:**
- Force-directed (default)
- Hierarchical (tree)
- Concentric

### 5.4 — Query & Chat (`/Query`)

**Purpose:** Ask questions, get answers with sources.

- Chat-style interface using `st.chat_message` + `st.chat_input`
- Each assistant message shows:
  - Answer text
  - Confidence badge (color-coded: green > 0.7, yellow > 0.4, red < 0.4)
  - Expandable "Sources" section with triplet list
  - Expandable "Entities found" section
- Top-K slider (1-20, default 5)
- Chat history persisted in `st.session_state`

### 5.5 — Documents (`/Documents`)

**Purpose:** Manage ingested documents.

- Table with columns: filename, chunks, triplets, actions
- "Delete" button per row with confirmation dialog
- "View graph" button → navigates to Graph page filtered to that document
- Bulk delete with multi-select

## 6. New Files

```
ui/
  __init__.py
  app.py                 # Streamlit entrypoint (main nav)
  pages/
    1_Upload.py          # Document upload page
    2_Graph.py           # Graph explorer
    3_Query.py           # Chat & query
    4_Documents.py       # Document management
  components/
    __init__.py
    api_client.py        # httpx wrapper for FastAPI calls
    graph_renderer.py    # Cytoscape graph building + styling
    sidebar.py           # Shared sidebar component
  styles/
    theme.toml           # Streamlit custom theme (dark mode)
Makefile                 # run, stop, clean, test commands
```

## 7. New API Endpoints (needed for graph visualization)

The current API doesn't expose the full graph for visualization. Add these endpoints:

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/api/v1/graph/entities` | List all entities with type, degree count |
| `GET` | `/api/v1/graph/edges` | List all edges (subject, predicate, object) with IDs |
| `GET` | `/api/v1/graph/subgraph?entity={id}&hops={n}` | Get N-hop neighborhood of an entity |
| `GET` | `/api/v1/graph/filters` | Available filter values: entity types, relation types, source docs |

**Response format for `/graph/edges`:**

```json
{
  "nodes": [
    {"id": "Python", "label": "Python", "type": "Technology", "degree": 5}
  ],
  "edges": [
    {"source": "Python", "target": "Guido_van_Rossum", "relation": "developed_by"}
  ]
}
```

## 8. Makefile

```makefile
.PHONY: run stop clean test seed init

run:                        ## Start everything
	docker compose up -d
	@sleep 2
	uv run python -c "from scripts.init_nebula import init_schema; init_schema()" 2>/dev/null || true
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 &
	uv run streamlit run ui/app.py --server.port 8501
	kill %1 2>/dev/null

stop:                       ## Stop all services
	docker compose down

clean:                      ## Full reset (deletes data)
	docker compose down -v
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null

test:                       ## Run unit tests
	uv run ruff check app/ tests/ && uv run ruff format app/ tests/ && uv run pytest tests/ -v

seed:                       ## Load sample data
	uv run python -c "from scripts.seed import seed; seed()"

init:                       ## Init NebulaGraph schema
	uv run python -c "from scripts.init_nebula import init_schema; init_schema()"
```

## 9. Dependencies to Add

```toml
# pyproject.toml [project.dependencies]
"streamlit>=1.38.0",
"streamlit-cytoscapejs>=0.3.0",
"httpx>=0.27.0",         # already in dev, move to main
```

## 10. Entity Type Color Map

```python
ENTITY_COLORS = {
    "Technology": "#4FC3F7",
    "Person": "#66BB6A",
    "Organization": "#FFA726",
    "Concept": "#AB47BC",
    "Product": "#EF5350",
    "Location": "#26C6DA",
    "Event": "#FFEE58",
    "Industry": "#8D6E63",
    "entity": "#90A4AE",   # default
}
```

## 11. Milestones

### Phase 6 — Streamlit Shell + Startup (U1)

- Create `ui/` structure with `app.py` (multipage nav)
- Create `Makefile` with `run`, `stop`, `clean`
- `api_client.py` with httpx wrapper
- Add new dependencies to `pyproject.toml`
- Verify `make run` works end-to-end

### Phase 7 — Upload + Document Management (U2, U5)

- Upload page with `st.file_uploader`
- Documents page with table + delete
- Dashboard with health check + stats
- Seed button on upload page

### Phase 8 — Graph Explorer (U3)

- New API endpoints for graph data
- `graph_renderer.py` — build Cytoscape elements from API response
- Graph page with interactive visualization
- Filters: by document, entity type, relation type, degree
- Click-to-inspect entity details
- Layout switcher

### Phase 9 — Query Chat (U4)

- Chat interface with `st.chat_message`
- Answer display with confidence badge
- Expandable sources + entities
- Chat history in session state

### Phase 10 — Polish

- Dark theme (`styles/theme.toml`)
- Error handling UI (toast notifications for API errors)
- Loading states and spinners
- Responsive layout
- Unit tests for `api_client.py` and `graph_renderer.py`

## 12. Tips & Recommendations

### What I'd recommend you also consider:

1. **Graph export** — Add a "Download as PNG/SVG" button on the graph page. Cytoscape supports this natively.

2. **Graph diff** — After uploading a new document, show a highlighted diff of what entities/edges were added. This gives immediate visual feedback of ingestion impact.

3. **Entity search + highlight** — Type an entity name, and the graph zooms + highlights that node and its neighborhood. Extremely useful for exploration.

4. **Query-to-graph** — When you get a query answer, add a button "Show in graph" that navigates to the Graph page with only the relevant subgraph highlighted (the entities found in the answer). This connects the chat experience to the visual exploration.

5. **Edge weight visualization** — You already store `weight` on edges. Use edge thickness to represent weight, and allow "merge similar edges" to deduplicate when multiple documents contribute the same relationship.

6. **Streaming answers** — Use `st.write_stream()` to show the LLM answer token-by-token instead of waiting for the full response. Much better UX for slow API calls.

7. **Sidebar status widget** — A persistent sidebar indicator showing backend health (green dot / red dot) so the user always knows if the system is responsive.

8. **Session state caching** — Cache graph data in `st.session_state` so you don't re-fetch the entire graph on every Streamlit re-run (which happens on every widget interaction).

9. **`st.data_editor` for documents** — Use Streamlit's editable dataframe for the Documents page instead of a static table. Allows inline actions.

10. **Configurable chunk settings** — Expose `CHUNK_SIZE` and `CHUNK_OVERLAP` as sidebar sliders in the Upload page so you can experiment with different chunking strategies without code changes.

## 13. Non-Functional Requirements

| Aspect | Requirement |
|--------|-------------|
| Startup | `make run` launches everything in < 30 seconds (excluding Docker image pulls) |
| Latency | Graph rendering must handle up to 500 nodes without lag |
| UX | Loading spinners on every API call, toast notifications on errors |
| State | Chat history survives page navigation within a session |
| Theme | Dark mode by default (knowledge graphs look better on dark backgrounds) |
