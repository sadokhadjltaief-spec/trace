"""STUB teacher/judge view: live posterior, IG choice, state, guard events, cost. Displays engine numbers only."""
import streamlit as st

import ui

ui.sidebar()
be = ui.backend()
st.title("Teacher / judge panel (stub)")
if "session" not in st.session_state:
    st.info("Start a session on the home page first.")
    st.stop()

s = be.get_state(st.session_state.session["session_id"])
ui.show_warnings(s)
c1, c2 = st.columns([2, 1])
with c1:
    st.subheader("Diagnosis (posterior from engine/bayes.py)")
    for h in s["posterior"]:
        st.progress(h["prob"], text=f"{h['id']} {h['name_en']}: {h['prob']:.2f}")
    nq = s["next_question"]
    if nq["stop"]:
        st.write(f"Stopped: {nq['stop_reason']}. Top: {s['top']['id']} ({s['top']['prob']:.2f}).")
    else:
        alts = ", ".join(f"{a['question_id']} {a['ig_bits']:.3f}" for a in nq["alternatives"])
        st.write(f"Next question **{nq['question_id']}** chosen because IG = {nq['ig_bits']:.3f} bits "
                 f"(alternatives: {alts}). Current entropy {nq['entropy_bits']:.3f} bits.")
with c2:
    st.metric("State", s["state"])
    st.write("Answers:")
    for r in s["asked"]:
        st.write(f"{r['question_id']}: {r['option']} ({r['confidence']}) {'✓' if r['correct'] else '✗'}")
    if s["fragile"]:
        st.write("Fragile (right but not sure): " + ", ".join(s["fragile"]))
    st.write("Guard events:")
    for g in s["guard_events"] or [{"summary": "none yet"}]:
        st.write(f"- {g['summary']}")
    c = s["cost"]
    st.caption(f"Session cost: {c['calls']} LLM calls ({c['cached_calls']} cached), "
               f"{c['prompt_tokens']}+{c['completion_tokens']} tokens. {c['label']}.")
