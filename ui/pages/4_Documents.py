import streamlit as st

from ui.components.sidebar import get_api_client

st.set_page_config(page_title="Documents — GraphRAG", page_icon="📁", layout="wide")

client = get_api_client()

st.title("Documents")
st.markdown("Manage ingested documents and view their graph connections.")

if "selected_doc" not in st.session_state:
    st.session_state.selected_doc = None

try:
    docs = client.list_documents()

    if not docs:
        st.info("No documents ingested yet. Go to **Upload** to add some.")
    else:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**{len(docs)} document(s)** ingested")
        with col2:
            total_triplets = sum(d.triplets_count for d in docs)
            total_chunks = sum(d.chunks_count for d in docs)
            st.metric("Total Triplets", total_triplets)
            st.metric("Total Chunks", total_chunks)

        st.divider()

        col_labels = st.columns([3, 1, 1, 1])
        with col_labels[0]:
            st.markdown("**File**")
        with col_labels[1]:
            st.markdown("**Chunks**")
        with col_labels[2]:
            st.markdown("**Triplets**")
        with col_labels[3]:
            st.markdown("**Actions**")
        st.divider()

        for doc in docs:
            cols = st.columns([3, 1, 1, 1])
            with cols[0]:
                is_selected = st.session_state.selected_doc == doc.filename
                if st.checkbox(
                    f"📄 {doc.filename}",
                    value=is_selected,
                    key=f"select_{doc.filename}",
                ):
                    st.session_state.selected_doc = doc.filename
                else:
                    if st.session_state.selected_doc == doc.filename:
                        st.session_state.selected_doc = None
            with cols[1]:
                st.markdown(f"{doc.chunks_count}")
            with cols[2]:
                st.markdown(f"{doc.triplets_count}")
            with cols[3]:
                if st.button("🗑️", key=f"del_{doc.filename}", help="Delete"):
                    try:
                        result = client.delete_document(doc.filename)
                        st.success(
                            f"Deleted {result['vectors_deleted']} vectors, "
                            f"{result['entities_deleted_from_graph']} entities"
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(f"Delete failed: {e}")
            st.divider()

        if st.session_state.selected_doc:
            st.markdown(f"### Selected: {st.session_state.selected_doc}")
            st.info("Go to **Graph** page to view this document's entities and relationships.")
            if st.button("View in Graph", type="primary"):
                st.switch_page("Graph")

except Exception as e:
    st.error(f"Could not load documents: {e}")
