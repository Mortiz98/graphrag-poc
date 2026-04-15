from __future__ import annotations

from streamlit_agraph import Config, Edge, Node

ENTITY_COLORS = {
    "Technology": "#4FC3F7",
    "Person": "#66BB6A",
    "Organization": "#FFA726",
    "Concept": "#AB47BC",
    "Product": "#EF5350",
    "Location": "#26C6DA",
    "Event": "#FFEE58",
    "Industry": "#8D6E63",
    "entity": "#90A4AE",
}


def get_node_color(entity_type: str) -> str:
    return ENTITY_COLORS.get(entity_type, ENTITY_COLORS["entity"])


def build_agraph_nodes(nodes: list[dict]) -> list[Node]:
    agraph_nodes = []
    for node in nodes:
        node_type = node.get("type", "entity")
        degree = node.get("degree", 0)
        size = min(10 + degree * 3, 40)
        agraph_nodes.append(
            Node(
                id=node["id"],
                label=node.get("label", node["id"]),
                size=size,
                color=get_node_color(node_type),
                meta={
                    "type": node_type,
                    "degree": degree,
                },
            )
        )
    return agraph_nodes


def build_agraph_edges(edges: list[dict]) -> list[Edge]:
    agraph_edges = []
    for edge in edges:
        agraph_edges.append(
            Edge(
                source=edge["source"],
                target=edge["target"],
                label=edge.get("relation", ""),
                type="CURVED_SMOOTH",
            )
        )
    return agraph_edges


def build_agraph_config(
    layout: str = "force-directed",
    physics: bool = True,
    height: int = 800,
) -> Config:
    direction = "LR" if layout == "hierarchical" else "UD"
    hierarchical_enabled = True if layout == "hierarchical" else False

    return Config(
        height=height,
        width=1600,
        directed=True,
        physics=physics,
        hierarchical=hierarchical_enabled,
        graph={"direction": direction},
        layout={"hierarchical": {"enabled": hierarchical_enabled}},
    )


def filter_graph(
    nodes: list[dict],
    edges: list[dict],
    entity_types: list[str] | None = None,
    relation_types: list[str] | None = None,
    min_degree: int = 0,
) -> tuple[list[dict], list[dict]]:
    if not entity_types and not relation_types and min_degree == 0:
        return nodes, edges

    entity_ids_to_keep = set()

    if entity_types:
        type_filtered = {n["id"] for n in nodes if n.get("type", "entity") in entity_types}
        entity_ids_to_keep |= type_filtered

    if min_degree > 0:
        degree_filtered = {n["id"] for n in nodes if (n.get("degree", 0)) >= min_degree}
        if entity_ids_to_keep:
            entity_ids_to_keep &= degree_filtered
        else:
            entity_ids_to_keep = degree_filtered

    if not entity_ids_to_keep:
        entity_ids_to_keep = {n["id"] for n in nodes}

    relation_filtered_edges = []
    if relation_types:
        relation_filtered_edges = [e for e in edges if e.get("relation") in relation_types]
    else:
        relation_filtered_edges = edges

    connected_ids = set()
    filtered_edges = []
    for edge in relation_filtered_edges:
        if edge["source"] in entity_ids_to_keep and edge["target"] in entity_ids_to_keep:
            filtered_edges.append(edge)
            connected_ids.add(edge["source"])
            connected_ids.add(edge["target"])

    filtered_nodes = [n for n in nodes if n["id"] in connected_ids]

    return filtered_nodes, filtered_edges
