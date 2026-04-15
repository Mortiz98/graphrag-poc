from __future__ import annotations

import streamlit as st

from ui.components.api_client import DEFAULT_BASE_URL, ApiClient


def get_api_client() -> ApiClient:
    if "api_client" not in st.session_state:
        st.session_state.api_client = ApiClient(base_url=DEFAULT_BASE_URL)
    return st.session_state.api_client


def render_sidebar() -> None:
    with st.sidebar:
        st.image("https://img.shields.io/badge/GraphRAG-PoC-blue", width=150)
        st.divider()

        client = get_api_client()
        try:
            health = client.health()
            qdrant_ok = health.qdrant == "ok"
            nebula_ok = health.nebulagraph == "ok"
            llm_ok = health.llm == "configured"

            st.markdown("**Services**")
            st.markdown(f"{'🟢' if qdrant_ok else '🔴'} Qdrant")
            st.markdown(f"{'🟢' if nebula_ok else '🔴'} NebulaGraph")
            st.markdown(f"{'🟢' if llm_ok else '🔴'} LLM (OpenRouter)")

            if not (qdrant_ok and nebula_ok):
                st.warning("Some services are unavailable. Run `docker compose up -d`.")

            if not llm_ok:
                st.warning("LLM not configured. Set OPENROUTER_API_KEY in .env.")
        except Exception:
            st.error("Backend API unreachable at " + DEFAULT_BASE_URL)
            st.caption("Start it with: `uv run uvicorn app.main:app --port 8000`")
