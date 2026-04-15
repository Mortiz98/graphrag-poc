import streamlit as st

from ui.components.sidebar import get_api_client, render_sidebar

st.set_page_config(
    page_title="GraphRAG",
    page_icon="🕸️",
    layout="wide",
    initial_sidebar_state="expanded",
)

render_sidebar()

client = get_api_client()

st.title("GraphRAG PoC")
st.markdown("Hybrid RAG system — Knowledge graph + vector search")

try:
    stats = client.graph_stats()
    docs = client.list_documents()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Documents", len(docs))
    with col2:
        st.metric("Entities", stats.entity_count)
    with col3:
        st.metric("Relations", stats.edge_count)
except Exception as e:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Documents", "—")
    with col2:
        st.metric("Entities", "—")
    with col3:
        st.metric("Relations", "—")
    st.caption(f"Could not load stats: {e}")

st.divider()

st.markdown(
    "Use the sidebar to navigate:\n"
    "- **Upload** — Ingest PDF, TXT, or Markdown documents\n"
    "- **Graph** — Explore the knowledge graph visually\n"
    "- **Query** — Ask questions and get answers with sources\n"
    "- **Documents** — Manage ingested documents"
)

st.divider()
st.markdown("### Recent Activity")

try:
    if docs:
        recent = sorted(docs, key=lambda d: d.filename, reverse=True)[:5]
        for doc in recent:
            st.markdown(f"- **{doc.filename}**: {doc.triplets_count} triplets, {doc.chunks_count} chunks")
    else:
        st.caption("No documents ingested yet.")
except Exception as e:
    st.caption(f"Could not load recent activity: {e}")
