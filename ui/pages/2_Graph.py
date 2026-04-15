import streamlit as st
from streamlit_agraph import ConfigBuilder, agraph

from ui.components.graph_renderer import (
    build_agraph_config,
    build_agraph_edges,
    build_agraph_nodes,
    filter_graph,
)
from ui.components.sidebar import get_api_client

st.set_page_config(page_title="Graph — GraphRAG", page_icon="🕸️", layout="wide")

client = get_api_client()

st.title("Knowledge Graph Explorer")
st.markdown("Interactive visualization of entities and relationships.")

try:
    filters = client.graph_filters()
    graph_data = client.graph_edges()
    stats = client.graph_stats()

    with st.sidebar:
        st.markdown("### Filters")

        entity_types = st.multiselect(
            "Entity Types",
            options=filters.entity_types,
            default=None,
            placeholder="All types",
        )

        relation_types = st.multiselect(
            "Relation Types",
            options=filters.relation_types,
            default=None,
            placeholder="All relations",
        )

        min_degree = st.slider("Min connections", 0, 20, 0)

        layout_options = ["force-directed", "hierarchical", "circular"]
        selected_layout = st.selectbox("Layout", layout_options, index=0)

        physics_enabled = st.toggle("Physics simulation", value=True)

        st.divider()
        st.markdown("### Graph Stats")
        st.metric("Entities", stats.entity_count)
        st.metric("Relations", stats.edge_count)

    nodes, edges = filter_graph(
        graph_data.nodes,
        graph_data.edges,
        entity_types=entity_types if entity_types else None,
        relation_types=relation_types if relation_types else None,
        min_degree=min_degree,
    )

    st.markdown(f"Showing **{len(nodes)}** entities and **{len(edges)}** relations")

    if not nodes:
        st.warning("No entities match the current filters. Adjust the filters or ingest more documents.")
    else:
        agraph_nodes = build_agraph_nodes(nodes)
        agraph_edges = build_agraph_edges(edges)

        config = build_agraph_config(
            layout=selected_layout,
            physics=physics_enabled,
            height=600,
        )
        config_builder = ConfigBuilder()
        config_builder.from_config(config)
        final_config = config_builder.build()

        selected_node = agraph(
            nodes=agraph_nodes,
            edges=agraph_edges,
            config=final_config,
        )

        if selected_node:
            st.session_state.selected_node_id = selected_node

        if "selected_node_id" in st.session_state and st.session_state.selected_node_id:
            st.divider()
            st.markdown("### Selected Entity")

            node_id = st.session_state.selected_node_id
            node_data = next((n for n in nodes if n["id"] == node_id), None)

            if node_data:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Name", node_data.get("label", node_id))
                with col2:
                    st.metric("Type", node_data.get("type", "entity"))
                with col3:
                    st.metric("Connections", node_data.get("degree", 0))

                connected_edges = [e for e in edges if e["source"] == node_id or e["target"] == node_id]
                if connected_edges:
                    st.markdown("**Connections:**")
                    for edge in connected_edges[:10]:
                        direction = "→" if edge["source"] == node_id else "←"
                        other = edge["target"] if edge["source"] == node_id else edge["source"]
                        st.markdown(f"- {node_id} {edge.get('relation', 'related')} {direction} {other}")

                if st.button("View 1-hop neighborhood"):
                    subgraph = client.graph_subgraph(node_id, hops=1)
                    st.session_state.subgraph_data = subgraph
                    st.rerun()

            if "subgraph_data" in st.session_state:
                st.divider()
                st.markdown("### Neighborhood View")
                sub_nodes = st.session_state.subgraph_data.nodes
                sub_edges = st.session_state.subgraph_data.edges
                st.caption(f"{len(sub_nodes)} entities, {len(sub_edges)} relations")

except Exception as e:
    st.error(f"Could not load graph: {e}")
    st.caption("Make sure Docker services are running and documents have been ingested.")
