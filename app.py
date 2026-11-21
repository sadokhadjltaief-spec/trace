"""TRACE: STUB home + onboarding. The teammate replaces this page; keep docs/INTERFACE.md."""
import streamlit as st

import ui

st.set_page_config(page_title="TRACE", page_icon="🔎", layout="wide")
ui.sidebar()
be = ui.backend()

st.title("TRACE (stub)")
st.caption("Stub page built on the engine contract. Real design comes from the frontend teammate.")

if "session" not in st.session_state:
    st.subheader("Onboarding (stub)")
    with st.form("onboarding"):
        name = st.text_input("Name", value="Amira")
        level = st.text_input("Level / class", value="7e")
        lang = st.selectbox("Language", ["fr", "ar", "en"])
        clear = st.checkbox("I like short, step-by-step explanations (clear and structured mode)")
        if st.form_submit_button("Continue →"):
            profile = {k: clear for k in ("literal_language", "one_question_per_message", "visible_agenda",
                                          "fixed_template", "neutral_feedback", "structured_why")}
            st.session_state.session = be.start_session({"name": name, "level": level, "lang": lang}, profile)
            st.rerun()
else:
    s = st.session_state.session
    st.subheader(f"Bonjour, {s['student']['name']}")
    ui.show_warnings(s)
    cols = st.columns(3)
    cols[0].page_link("pages/1_Learn.py", label="Diagnose me")
    cols[1].page_link("pages/2_Judge_Panel.py", label="Teacher / judge panel")
    cols[2].page_link("pages/3_Results.py", label="Results")
    cols = st.columns(3)
    cols[0].page_link("pages/4_Report.py", label="Report")
    cols[1].page_link("pages/5_Study_Studio.py", label="Study Studio")
    if cols[2].button("Restart session"):
        del st.session_state["session"]
        st.rerun()
