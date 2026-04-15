import streamlit as st

from ui.components.sidebar import get_api_client

st.set_page_config(page_title="Graph — GraphRAG", page_icon="🕸️", layout="wide")

client = get_api_client()

st.title("Knowledge Graph Explorer")

st.info("Graph visualization will be available after Phase 8. Upload documents first to populate the graph.")

try:
    stats = client.graph_stats()
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Entities", stats.entity_count)
    with col2:
        st.metric("Relations", stats.edge_count)
    st.caption(f"Space: {stats.space}")
except Exception as e:
    st.error(f"Could not load graph stats: {e}")
