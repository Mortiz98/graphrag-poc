import streamlit as st

from ui.components.sidebar import get_api_client

st.set_page_config(page_title="Query — GraphRAG", page_icon="💬", layout="wide")

client = get_api_client()

st.title("Query & Chat")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and "confidence" in msg:
            conf = msg["confidence"]
            color = "green" if conf > 0.7 else "orange" if conf > 0.4 else "red"
            st.markdown(f"Confidence: :{color}[{conf:.0%}]")
        if msg["role"] == "assistant" and "sources" in msg and msg["sources"]:
            with st.expander("Sources"):
                for src in msg["sources"]:
                    st.markdown(f"**{src.get('document', '')}** (chunk `{src.get('chunk_id', '')[:8]}...`)")
                    for t in src.get("triplets", []):
                        st.markdown(f"  - {t['subject']} → {t['predicate']} → {t['object']}")
        if msg["role"] == "assistant" and "entities" in msg and msg["entities"]:
            with st.expander("Entities found"):
                st.markdown(", ".join(msg["entities"]))

top_k = st.sidebar.slider("Top-K results", 1, 20, 5)
use_streaming = st.sidebar.toggle("Streaming response", value=True)

if prompt := st.chat_input("Ask a question..."):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        if use_streaming:
            try:
                full_response = ""
                response_placeholder = st.empty()

                with st.spinner("Generating response..."):
                    for token in client.query_stream(prompt, top_k=top_k):
                        full_response += token
                        response_placeholder.markdown(full_response + "▌")

                response_placeholder.markdown(full_response)
                conf = 0.5
                sources = []
                entities = []

            except Exception as e:
                st.error(f"Query failed: {e}")
                st.toast(f"Error: {e}", icon="❌")
                full_response = f"Error: {e}"
        else:
            try:
                with st.spinner("Thinking..."):
                    result = client.query(prompt, top_k=top_k)

                full_response = result.answer
                conf = result.confidence
                sources = result.sources
                entities = result.entities_found
                st.markdown(full_response)

                color = "green" if conf > 0.7 else "orange" if conf > 0.4 else "red"
                st.markdown(f"Confidence: :{color}[{conf:.0%}]")

                if sources:
                    with st.expander("Sources"):
                        for src in sources:
                            st.markdown(f"**{src.get('document', '')}** (chunk `{src.get('chunk_id', '')[:8]}...`)")
                            for t in src.get("triplets", []):
                                st.markdown(f"  - {t['subject']} → {t['predicate']} → {t['object']}")

                if entities:
                    with st.expander("Entities found"):
                        st.markdown(", ".join(entities))

            except Exception as e:
                st.error(f"Query failed: {e}")
                st.toast(f"Error: {e}", icon="❌")
                full_response = f"Error: {e}"

        st.session_state.chat_history.append(
            {
                "role": "assistant",
                "content": full_response,
                "confidence": conf if "conf" in locals() else 0.5,
                "sources": sources if "sources" in locals() else [],
                "entities": entities if "entities" in locals() else [],
            }
        )

if st.sidebar.button("Clear chat"):
    st.session_state.chat_history = []
    st.toast("Chat cleared", icon="🗑️")
    st.rerun()
