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

if prompt := st.chat_input("Ask a question..."):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                result = client.query(prompt, top_k=top_k)
                answer = result.answer
                st.markdown(answer)

                conf = result.confidence
                color = "green" if conf > 0.7 else "orange" if conf > 0.4 else "red"
                st.markdown(f"Confidence: :{color}[{conf:.0%}]")

                if result.sources:
                    with st.expander("Sources"):
                        for src in result.sources:
                            st.markdown(f"**{src.get('document', '')}** (chunk `{src.get('chunk_id', '')[:8]}...`)")
                            for t in src.get("triplets", []):
                                st.markdown(f"  - {t['subject']} → {t['predicate']} → {t['object']}")

                if result.entities_found:
                    with st.expander("Entities found"):
                        st.markdown(", ".join(result.entities_found))

                st.session_state.chat_history.append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "confidence": conf,
                        "sources": result.sources,
                        "entities": result.entities_found,
                    }
                )
            except Exception as e:
                st.error(f"Query failed: {e}")
