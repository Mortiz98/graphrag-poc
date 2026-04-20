import streamlit as st

from ui.components.sidebar import get_api_client

st.set_page_config(page_title="Query — GraphRAG", page_icon="💬", layout="wide")

client = get_api_client()

st.title("Query & Chat")

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "agent_session_ids" not in st.session_state:
    st.session_state.agent_session_ids = {"support": None, "am": None}

agent_choice = st.sidebar.selectbox(
    "Agent",
    ["support", "am"],
    format_func=lambda x: "Support Agent" if x == "support" else "Account Manager",
)

if agent_choice == "am":
    account_id = st.sidebar.text_input("Account ID", value="acme_corp")
else:
    account_id = None

use_streaming = st.sidebar.toggle("Streaming response", value=True)

if st.sidebar.button("New session"):
    st.session_state.agent_session_ids[agent_choice] = None
    st.toast("Session reset", icon="🔄")

if st.sidebar.button("Clear chat"):
    st.session_state.chat_history = []
    st.toast("Chat cleared", icon="🗑️")
    st.rerun()

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("Ask a question..."):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        session_id = st.session_state.agent_session_ids.get(agent_choice)
        full_response = ""

        if use_streaming:
            try:
                response_placeholder = st.empty()

                with st.spinner("Generating response..."):
                    for event in client.agent_query_stream(
                        prompt,
                        agent=agent_choice,
                        session_id=session_id,
                        account_id=account_id,
                    ):
                        if event.get("type") == "metadata":
                            new_sid = event.get("session_id")
                            if new_sid:
                                st.session_state.agent_session_ids[agent_choice] = new_sid
                        elif event.get("type") == "token":
                            full_response += event.get("content", "")
                            response_placeholder.markdown(full_response + "▌")
                        elif event.get("type") == "done":
                            break

                response_placeholder.markdown(full_response)

            except Exception as e:
                st.error(f"Agent error: {e}")
                full_response = f"Error: {e}"
        else:
            try:
                with st.spinner("Thinking..."):
                    result = client.agent_query(
                        prompt,
                        agent=agent_choice,
                        session_id=session_id,
                        account_id=account_id,
                    )

                if result.session_id and not session_id:
                    st.session_state.agent_session_ids[agent_choice] = result.session_id
                full_response = result.answer
                st.markdown(full_response)

            except Exception as e:
                st.error(f"Agent error: {e}")
                full_response = f"Error: {e}"

        st.session_state.chat_history.append(
            {
                "role": "assistant",
                "content": full_response,
            }
        )
