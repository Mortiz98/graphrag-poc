from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.core.graph import get_nebula_session
from app.core.vectorstore import get_qdrant_client
from app.models.graph_schema import EDGE_RELATED_TO, SPACE_NAME

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


def _get_degree(session, entity_id: str) -> int:
    query_out = f'GO FROM "{entity_id}" OVER {EDGE_RELATED_TO} YIELD vertex AS v'
    result = session.execute(query_out)
    out_count = len(result.rows()) if result.is_succeeded() else 0

    query_in = f'GO FROM "{entity_id}" OVER {EDGE_RELATED_TO} REVERSELY YIELD vertex AS v'
    result = session.execute(query_in)
    in_count = len(result.rows()) if result.is_succeeded() else 0

    return out_count + in_count


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

            result = session.execute("MATCH (n:entity) RETURN n.name AS name, n.type AS type")
            if not result.is_succeeded():
                raise HTTPException(status_code=500, detail="Query failed")

            entities = []
            for row in result.rows():
                try:
                    name_val = row.values[0].get_sVal()
                    name = name_val.decode() if isinstance(name_val, bytes) else str(name_val)

                    type_val = row.values[1].get_sVal()
                    entity_type = type_val.decode() if isinstance(type_val, bytes) else str(type_val)

                    degree = _get_degree(session, name)

                    entities.append(
                        {
                            "id": name,
                            "name": name,
                            "type": entity_type,
                            "degree": degree,
                        }
                    )
                except Exception:
                    continue

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

            query = "MATCH (s:entity)-[r:related_to]->(t:entity) RETURN s.name AS src, r.relation AS rel, t.name AS dst"
            result = session.execute(query)

            nodes_map = {}
            edges = []

            if result.is_succeeded():
                for row in result.rows():
                    try:
                        src_val = row.values[0].get_sVal()
                        src = src_val.decode() if isinstance(src_val, bytes) else str(src_val)

                        rel_val = row.values[1].get_sVal()
                        rel = rel_val.decode() if isinstance(rel_val, bytes) else str(rel_val)

                        dst_val = row.values[2].get_sVal()
                        dst = dst_val.decode() if isinstance(dst_val, bytes) else str(dst_val)

                        if src not in nodes_map:
                            nodes_map[src] = {"id": src, "label": src, "type": "entity", "degree": 0}
                        if dst not in nodes_map:
                            nodes_map[dst] = {"id": dst, "label": dst, "type": "entity", "degree": 0}

                        edges.append({"source": src, "target": dst, "relation": rel})
                    except Exception:
                        continue

            nodes = list(nodes_map.values())

            for edge in edges:
                if edge["source"] in nodes_map:
                    nodes_map[edge["source"]]["degree"] += 1
                if edge["target"] in nodes_map:
                    nodes_map[edge["target"]]["degree"] += 1

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

                for ent_id in current_layer:
                    if ent_id in visited:
                        continue
                    visited.add(ent_id)

                    name_query = f'FETCH PROP ON entity "{ent_id}" YIELD vertex AS v'
                    name_result = session.execute(name_query)

                    ent_name = ent_id
                    ent_type = "entity"
                    if name_result.is_succeeded() and name_result.rows():
                        try:
                            vertex = name_result.rows()[0].values[0].as_node()
                            props = vertex.properties
                            if "name" in props:
                                n_val = props["name"].get_sVal()
                                ent_name = n_val.decode() if isinstance(n_val, bytes) else str(n_val)
                            if "type" in props:
                                t_val = props["type"].get_sVal()
                                ent_type = t_val.decode() if isinstance(t_val, bytes) else str(t_val)
                        except Exception:
                            pass

                    if ent_id not in nodes_map:
                        nodes_map[ent_id] = {"id": ent_id, "label": ent_name, "type": ent_type, "degree": 0}

                    out_query = f'GO FROM "{ent_id}" OVER {EDGE_RELATED_TO} YIELD src, dst, relation'
                    out_result = session.execute(out_query)
                    if out_result.is_succeeded():
                        for row in out_result.rows():
                            try:
                                dst_val = row.values[1].get_sVal()
                                dst = dst_val.decode() if isinstance(dst_val, bytes) else str(dst_val)

                                rel_val = row.values[2].get_sVal()
                                rel = rel_val.decode() if isinstance(rel_val, bytes) else str(rel_val)

                                edges.append({"source": ent_id, "target": dst, "relation": rel})

                                if dst not in nodes_map:
                                    nodes_map[dst] = {"id": dst, "label": dst, "type": "entity", "degree": 0}

                                next_layer.add(dst)
                            except Exception:
                                continue

                    in_query = f'GO FROM "{ent_id}" OVER {EDGE_RELATED_TO} REVERSELY YIELD src, dst, relation'
                    in_result = session.execute(in_query)
                    if in_result.is_succeeded():
                        for row in in_result.rows():
                            try:
                                src_val = row.values[0].get_sVal()
                                src = src_val.decode() if isinstance(src_val, bytes) else str(src_val)

                                rel_val = row.values[2].get_sVal()
                                rel = rel_val.decode() if isinstance(rel_val, bytes) else str(rel_val)

                                edges.append({"source": src, "target": ent_id, "relation": rel})

                                if src not in nodes_map:
                                    nodes_map[src] = {"id": src, "label": src, "type": "entity", "degree": 0}

                                next_layer.add(src)
                            except Exception:
                                continue

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

            type_result = session.execute("MATCH (n:entity) RETURN DISTINCT n.type AS type")
            if type_result.is_succeeded():
                for row in type_result.rows():
                    try:
                        t_val = row.values[0].get_sVal()
                        t = t_val.decode() if isinstance(t_val, bytes) else str(t_val)
                        if t:
                            entity_types.add(t)
                    except Exception:
                        continue

            rel_result = session.execute(f"MATCH ()-[r:{EDGE_RELATED_TO}]->() RETURN DISTINCT r.relation AS rel")
            if rel_result.is_succeeded():
                for row in rel_result.rows():
                    try:
                        r_val = row.values[0].get_sVal()
                        r = r_val.decode() if isinstance(r_val, bytes) else str(r_val)
                        if r:
                            relation_types.add(r)
                    except Exception:
                        continue

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
