"""STUB student view: question, options, Sure/Not sure (required), Why?, tutor message."""
import streamlit as st

import ui

ui.sidebar()
be = ui.backend()
st.title("Learn (stub)")
if "session" not in st.session_state:
    st.info("Start a session on the home page first.")
    st.stop()

sid = st.session_state.session["session_id"]
s = be.get_state(sid)
ui.show_warnings(s)
a = s["agenda"]
if s["profile"].get("visible_agenda"):
    st.caption(f"Step {a['step']} of {a['total']}. Next: {a['next']}.")

turn = st.session_state.get("last_turn")
if turn:
    ui.show_text(turn["message"])
    st.caption(turn["grading"]["label"])

q = s["current_question"]
if not q:
    st.success("Diagnosis finished. See the teacher/judge panel or the report.")
    st.stop()

st.markdown(ui.latex_to_md(q["text"]))
with st.form(f"q_{q['id']}_{len(s['asked'])}"):
    opt = st.radio("Your answer", list(q["options"]), format_func=lambda k: f"{k}: {ui.latex_to_md(q['options'][k])}",
                   index=None)
    conf = st.radio("How sure are you?", ["sure", "unsure"], index=None, horizontal=True,
                    format_func=lambda c: {"sure": "Sure", "unsure": "Not sure"}[c])
    if q["why_mode"] == "structured":
        why = st.radio("Why?", [w["text"] for w in q["why_options"] if w["shown_allowed"]], index=None)
    else:
        why = st.text_area("Why? (explain in your own words)")
    if st.form_submit_button("Submit"):
        if opt is None or conf is None:
            st.error("Choose an answer and Sure / Not sure first.")
        else:
            st.session_state.last_turn = be.submit_answer(sid, q["id"], opt, conf, why or None)
            st.rerun()
