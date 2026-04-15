import streamlit as st

from ui.components.sidebar import get_api_client

st.set_page_config(page_title="Upload — GraphRAG", page_icon="📤", layout="wide")

client = get_api_client()

st.title("Upload Documents")
st.markdown("Upload PDF, TXT, or Markdown files to ingest into the knowledge graph.")

col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("### Upload Files")
with col2:
    st.markdown("### Quick Actions")
    if st.button("📥 Seed Sample Data", use_container_width=True):
        try:
            with st.spinner("Loading sample data..."):
                result = client.seed()
            st.success(f"**{result.filename}** — {result.chunks_count} chunks, {result.triplets_count} triplets")
            st.rerun()
        except Exception as e:
            st.toast(f"Seed failed: {e}", icon="❌")

uploaded_files = st.file_uploader(
    "Choose files",
    type=["pdf", "txt", "md"],
    accept_multiple_files=True,
)

if uploaded_files:
    st.divider()
    st.markdown("### Processing")

    success_count = 0
    error_count = 0

    for uploaded in uploaded_files:
        with st.spinner(f"Processing {uploaded.name}..."):
            try:
                result = client.ingest(
                    filename=uploaded.name,
                    content=uploaded.getvalue(),
                    content_type=uploaded.type or "application/octet-stream",
                )
                st.success(
                    f"**{result.filename}** — {result.chunks_count} chunks, "
                    f"{result.triplets_count} triplets ({result.status})"
                )
                success_count += 1
            except Exception as e:
                st.error(f"Error processing {uploaded.name}: {e}")
                error_count += 1

    if success_count > 0:
        st.toast(f"Successfully processed {success_count} file(s)", icon="✅")
    if error_count > 0:
        st.toast(f"Failed to process {error_count} file(s)", icon="❌")

    if success_count > 0:
        st.rerun()
