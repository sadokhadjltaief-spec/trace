"""STUB results page: reads results/*.json (read-only) and shows each number with its script."""
import streamlit as st

import ui

ui.sidebar()
be = ui.backend()
st.title("Results (stub)")
names = be.list_results()
if not names:
    st.info("No results yet.")
    st.stop()
for name in names:
    r = be.read_results(name)
    with st.expander(f"results/{name}.json: produced by {r.get('script', '?')}", expanded=True):
        if r.get("label"):
            st.caption(r["label"])
        if name == "diagnosis":
            rows = [{"limit": cap, "condition": c, "accuracy": v["accuracy"], "95% CI": v["accuracy_ci95"],
                     "questions": v["questions_used"]["mean"], "reached 0.85": v["reached_threshold_rate"]}
                    for cap, cs in r["conditions"].items() for c, v in cs.items()]
            st.dataframe(rows, hide_index=True)
            for cav in r.get("caveats", []):
                st.caption(f"Caveat: {cav}")
        else:
            st.json(r, expanded=False)
