"""STUB one-page report (SessionSummary). Real engine data since step 9 (teammate replaces the page)."""
import streamlit as st

import ui

ui.sidebar()
be = ui.backend()
st.title("Report (stub)")
if "session" not in st.session_state:
    st.info("Start a session on the home page first.")
    st.stop()
try:
    r = be.summary(st.session_state.session["session_id"])
except NotImplementedError as e:
    st.info(f"Not built yet in the engine: {e}. Switch Data to 'fake fixtures' to see the shape.")
    st.stop()

st.subheader(f"Misconception found: {r['diagnosis_names']['name_en']} ({r['diagnosis']['prob']:.2f})")
st.write(f"Status: {r['status']}")
st.write("Evidence:")
for e in r["evidence"]:
    st.write(f"- {e}")
st.write("Tried: " + " → ".join(r["tried"]))
ui.show_text(r["outcome"])
ui.show_text(r["next_step"])
for ref in r["lesson_refs"]:
    st.caption(f"Lesson: {ref['file']} p.{ref['page']}: {ref['snippet']}")
if r["handoff_note"]:
    ui.show_text(r["handoff_note"])
c = r["calibration"]
st.caption(f"Calibration: sure answers right {c['sure_correct']}/{c['sure_total']}, "
           f"not-sure answers right {c['unsure_correct']}/{c['unsure_total']}.")
