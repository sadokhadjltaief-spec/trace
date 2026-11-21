"""STUB Study Studio (StudioOutput). Fake data until step 12."""
import streamlit as st

import ui

ui.sidebar()
be = ui.backend()
st.title("Study Studio (stub)")
if "session" not in st.session_state:
    st.info("Start a session on the home page first.")
    st.stop()

tool = st.selectbox("Tool", ["flashcards", "summary", "quiz", "slides", "pdf", "diagram", "mindmap", "video", "podcast"])
allow = st.checkbox("Source folder allows derived material", value=True)
if st.button("Generate"):
    try:
        st.session_state.studio = be.studio_generate(st.session_state.session["session_id"], tool,
                                                     {"kind": "diagnosis", "folder_allow_derivatives": allow})
    except NotImplementedError as e:
        st.info(f"Not built yet in the engine: {e}. Switch Data to 'fake fixtures' to see the shape.")

out = st.session_state.get("studio")
if out:
    if out["refused"]:
        st.error(out["refused"])
        st.stop()
    if out["targeted_at"]:
        st.markdown(f"**Targeted at: {out['targeted_at']['name_en']}**")
    for it in out["items"]:
        with st.container(border=True):
            for k, v in it.items():
                if isinstance(v, dict) and "shown_allowed" in v:
                    st.caption(k)
                    ui.show_text(v)
    st.caption("Sources: " + "; ".join(f"{s['file']} p.{s['page']}" for s in out["sources"]))
    for f in out["files"]:
        st.caption(f"File: {f['path']} ({f['mime']})")
