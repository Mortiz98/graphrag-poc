from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.core.graph import get_nebula_session
from app.core.vectorstore import get_qdrant_client
from app.models.graph_schema import EDGE_RELATED_TO, SPACE_NAME, escape_ngql

router = APIRouter(prefix="/api/v1", tags=["graph"])


class Node(BaseModel):
    id: str
    label: str
    type: str
    degree: int


class Edge(BaseModel):
    source: str
    target: str
    relation: str


class GraphEdgesResponse(BaseModel):
    nodes: list[dict]
    edges: list[dict]


class GraphEntitiesResponse(BaseModel):
    entities: list[dict]


class GraphSubgraphResponse(BaseModel):
    nodes: list[dict]
    edges: list[dict]


class GraphFiltersResponse(BaseModel):
    entity_types: list[str]
    relation_types: list[str]
    source_docs: list[str]


def _extract_vertex(value) -> tuple[str, str, str] | None:
    """Extract vid, name, type from a NebulaGraph vertex Value.

    Returns (vid, name, type) or None if extraction fails.
    """
    try:
        vertex = value.get_vVal()
    except Exception:
        return None

    if not vertex:
        return None

    try:
        vid_bytes = vertex.vid.get_sVal()
        vid = vid_bytes.decode() if isinstance(vid_bytes, bytes) else str(vid_bytes)
    except Exception:
        vid = ""

    for tag in vertex.tags:
        if tag.name == b"entity":
            name = tag.props.get(b"name")
            entity_type = tag.props.get(b"type")
            name_str = name.get_sVal().decode() if name and name.get_sVal() else vid
            type_str = entity_type.get_sVal().decode() if entity_type and entity_type.get_sVal() else "entity"
            return vid, name_str, type_str

    return vid, vid, "entity"


def _build_all_nodes(session) -> tuple[dict[str, dict], dict[str, str]]:
    """Load all vertices with their properties.

    Returns:
        nodes_map: {vid: {"id": vid, "label": name, "type": type, "degree": 0}}
        vid_to_name: {vid: name}
    """
    result = session.execute("MATCH (n) RETURN n")
    nodes_map = {}
    vid_to_name = {}

    if result.is_succeeded():
        for row in result.rows():
            extracted = _extract_vertex(row.values[0])
            if not extracted:
                continue
            vid, name, entity_type = extracted
            if vid not in nodes_map:
                nodes_map[vid] = {
                    "id": vid,
                    "label": name,
                    "type": entity_type,
                    "degree": 0,
                }
            vid_to_name[vid] = name

    return nodes_map, vid_to_name


def _load_all_edges(session, vid_to_name: dict[str, str]) -> list[dict]:
    """Load all related_to edges using MATCH, converting VIDs to names."""
    result = session.execute("MATCH (s)-[r:related_to]->(t) RETURN s, r, t")
    edges = []

    if result.is_succeeded():
        for row in result.rows():
            try:
                src_extracted = _extract_vertex(row.values[0])
                dst_extracted = _extract_vertex(row.values[2])

                if not src_extracted or not dst_extracted:
                    continue

                src_vid, src_name, _ = src_extracted
                dst_vid, dst_name, _ = dst_extracted

                rel = ""
                edge = row.values[1].get_eVal()
                if edge:
                    rel_prop = edge.props.get(b"relation")
                    if rel_prop and rel_prop.get_sVal():
                        rel = rel_prop.get_sVal().decode()

                edges.append({"source": src_vid, "target": dst_vid, "relation": rel})
            except Exception:
                continue

    return edges


def _load_edges_by_go(session, vid: str, direction: str = "out") -> list[dict]:
    """Load edges from a vertex using GO query (for subgraph traversal).

    direction: 'out' or 'in'
    Returns list of {source_vid, target_vid, source_name, target_name, relation}
    """
    safe_vid = escape_ngql(vid)
    if direction == "out":
        query = (
            f'GO FROM "{safe_vid}" OVER {EDGE_RELATED_TO} '
            f"YIELD {EDGE_RELATED_TO}._src AS src, "
            f"{EDGE_RELATED_TO}._dst AS dst, "
            f"{EDGE_RELATED_TO}.relation AS rel"
        )
    else:
        query = (
            f'GO FROM "{safe_vid}" OVER {EDGE_RELATED_TO} REVERSELY '
            f"YIELD {EDGE_RELATED_TO}._src AS src, "
            f"{EDGE_RELATED_TO}._dst AS dst, "
            f"{EDGE_RELATED_TO}.relation AS rel"
        )

    result = session.execute(query)
    edges = []

    if result.is_succeeded():
        for row in result.rows():
            try:
                src_vid_val = row.values[0].get_sVal()
                src = src_vid_val.decode() if isinstance(src_vid_val, bytes) else str(src_vid_val)

                dst_vid_val = row.values[1].get_sVal()
                dst = dst_vid_val.decode() if isinstance(dst_vid_val, bytes) else str(dst_vid_val)

                rel_val = row.values[2].get_sVal()
                rel = rel_val.decode() if isinstance(rel_val, bytes) else str(rel_val)

                if direction == "out":
                    edges.append({"source_vid": src, "target_vid": dst, "relation": rel})
                else:
                    edges.append({"source_vid": src, "target_vid": dst, "relation": rel})
            except Exception:
                continue

    return edges


def _fetch_vertex_name(session, vid: str) -> tuple[str, str]:
    """Fetch entity name and type for a given VID using MATCH."""
    safe_vid = escape_ngql(vid)
    result = session.execute(f'MATCH (n) WHERE id(n) == "{safe_vid}" RETURN n LIMIT 1')
    if result.is_succeeded() and result.rows():
        extracted = _extract_vertex(result.rows()[0].values[0])
        if extracted:
            _, name, entity_type = extracted
            if not name:
                name = vid.replace("_", " ")
            return name, entity_type
    return vid.replace("_", " "), "entity"


@router.get(
    "/graph/entities",
    response_model=GraphEntitiesResponse,
    summary="List all entities",
    description="Returns all entities in the knowledge graph with their types and degrees.",
)
async def list_entities():
    try:
        with get_nebula_session() as session:
            session.execute(f"USE {SPACE_NAME}")

            nodes_map, _ = _build_all_nodes(session)
            edges = _load_all_edges(session, {})

            for edge in edges:
                if edge["source"] in nodes_map:
                    nodes_map[edge["source"]]["degree"] += 1
                if edge["target"] in nodes_map:
                    nodes_map[edge["target"]]["degree"] += 1

            entities = list(nodes_map.values())
            return GraphEntitiesResponse(entities=entities)

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"NebulaGraph unavailable: {e}")


@router.get(
    "/graph/edges",
    response_model=GraphEdgesResponse,
    summary="List all edges",
    description="Returns all edges (relationships) in the knowledge graph.",
)
async def list_edges():
    try:
        with get_nebula_session() as session:
            session.execute(f"USE {SPACE_NAME}")

            nodes_map, _ = _build_all_nodes(session)
            edges = _load_all_edges(session, {})

            for edge in edges:
                if edge["source"] in nodes_map:
                    nodes_map[edge["source"]]["degree"] += 1
                if edge["target"] in nodes_map:
                    nodes_map[edge["target"]]["degree"] += 1

            nodes = list(nodes_map.values())
            return GraphEdgesResponse(nodes=nodes, edges=edges)

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"NebulaGraph unavailable: {e}")


@router.get(
    "/graph/subgraph",
    response_model=GraphSubgraphResponse,
    summary="Get N-hop subgraph around an entity",
    description="Returns the neighborhood of a specific entity within N hops.",
)
async def get_subgraph(entity: str, hops: int = 1):
    try:
        with get_nebula_session() as session:
            session.execute(f"USE {SPACE_NAME}")

            visited = set()
            nodes_map = {}
            edges = []

            current_layer = {entity}
            for _ in range(hops):
                if not current_layer:
                    break
                next_layer = set()

                for vid in current_layer:
                    if vid in visited:
                        continue
                    visited.add(vid)

                    ent_name, ent_type = _fetch_vertex_name(session, vid)
                    if vid not in nodes_map:
                        nodes_map[vid] = {
                            "id": vid,
                            "label": ent_name,
                            "type": ent_type,
                            "degree": 0,
                        }

                    out_edges = _load_edges_by_go(session, vid, direction="out")
                    for e in out_edges:
                        dst_vid = e["target_vid"]
                        edges.append({"source": vid, "target": dst_vid, "relation": e["relation"]})
                        if dst_vid not in nodes_map:
                            name, typ = _fetch_vertex_name(session, dst_vid)
                            nodes_map[dst_vid] = {"id": dst_vid, "label": name, "type": typ, "degree": 0}
                        next_layer.add(dst_vid)

                    in_edges = _load_edges_by_go(session, vid, direction="in")
                    for e in in_edges:
                        src_vid = e["source_vid"]
                        edges.append({"source": src_vid, "target": vid, "relation": e["relation"]})
                        if src_vid not in nodes_map:
                            name, typ = _fetch_vertex_name(session, src_vid)
                            nodes_map[src_vid] = {"id": src_vid, "label": name, "type": typ, "degree": 0}
                        next_layer.add(src_vid)

                current_layer = next_layer

            for edge in edges:
                if edge["source"] in nodes_map:
                    nodes_map[edge["source"]]["degree"] += 1
                if edge["target"] in nodes_map:
                    nodes_map[edge["target"]]["degree"] += 1

            nodes = list(nodes_map.values())
            return GraphSubgraphResponse(nodes=nodes, edges=edges)

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"NebulaGraph unavailable: {e}")


@router.get(
    "/graph/filters",
    response_model=GraphFiltersResponse,
    summary="Get available filter values",
    description="Returns available entity types, relation types, and source documents for filtering.",
)
async def get_filters():
    settings = get_settings()
    entity_types = set()
    relation_types = set()
    source_docs = set()

    try:
        with get_nebula_session() as session:
            session.execute(f"USE {SPACE_NAME}")

            nodes_map, _ = _build_all_nodes(session)

            for node_data in nodes_map.values():
                if node_data["type"]:
                    entity_types.add(node_data["type"])

            edges = _load_all_edges(session, {})
            for edge in edges:
                if edge["relation"]:
                    relation_types.add(edge["relation"])

    except Exception:
        pass

    try:
        client = get_qdrant_client()
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]

        if settings.qdrant_collection_name in collection_names:
            all_points = []
            offset = None
            while True:
                results = client.scroll(
                    collection_name=settings.qdrant_collection_name,
                    limit=100,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                all_points.extend(results[0])
                if not results[1]:
                    break
                offset = results[1]

            for point in all_points:
                source = point.payload.get("source_doc", "")
                if source:
                    source_docs.add(source)

    except Exception:
        pass

    return GraphFiltersResponse(
        entity_types=sorted(entity_types),
        relation_types=sorted(relation_types),
        source_docs=sorted(source_docs),
    )
