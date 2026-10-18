"""Read-only public showcase; the local application remains the full product."""

import os
from pathlib import Path

import streamlit as st

from ai_service import ModelCallError, analyze_complaint
from database import Database
from schemas import JOB_STATUS_LABELS

DEMO_DATABASE = Path(__file__).with_name("public_demo.db")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")
DEMO_AI_ENABLED = os.getenv("REPAIRDESK_DEMO_AI", "false").lower() == "true"


@st.cache_resource
def get_demo_database() -> Database:
    return Database(DEMO_DATABASE, read_only=True)


st.set_page_config(
    page_title="RepairDesk Local · Public Demo",
    page_icon="🔧",
    layout="wide",
)

st.title("RepairDesk Local")
st.caption("Public demo · Fictional sample jobs · Read-only")
st.info(
    "This is a public showcase with fictional records. Customer intake, edits, "
    "estimates, and saved analyses are disabled. Use the local installation for "
    "private shop work."
)

db = get_demo_database()
jobs = db.search()
if not jobs:
    st.error("The sample database is empty. The demo deployment needs its sample data.")
    st.stop()

counts = db.counts()
total, waiting, active, completed = st.columns(4)
total.metric("Sample jobs", counts["total"])
waiting.metric("Awaiting inspection", counts["awaiting_inspection"])
active.metric("In progress", counts["in_progress"])
completed.metric("Completed", counts["completed"])

st.subheader("Fictional repair jobs")
st.dataframe(
    [
        {
            "Repair": job["id"],
            "Customer": job["customer_name"] or job["customer_reference"],
            "Device": f'{job["brand"]} {job["model"]}',
            "Category": job["device_category"].title(),
            "Status": JOB_STATUS_LABELS[job["status"]],
        }
        for job in jobs
    ],
    hide_index=True,
    width="stretch",
)

jobs_by_id = {job["id"]: job for job in jobs}
selected_id = st.selectbox(
    "Explore a sample record",
    options=list(jobs_by_id),
    format_func=lambda job_id: (
        f'{job_id} · {jobs_by_id[job_id]["brand"]} '
        f'{jobs_by_id[job_id]["model"]}'
    ),
)
job = db.get_job(selected_id)
st.subheader(f'{job["brand"]} {job["model"]} · {job["device_category"].title()}')
st.caption(f'{job["id"]} · {JOB_STATUS_LABELS[job["status"]]}')
st.markdown("**Reported issue**")
st.write(job["complaint"])
st.markdown("**Visible damage**")
st.write(job["visible_damage"] or "None recorded.")
st.markdown("**Accessories received**")
st.write(job["accessories"] or "None recorded.")

if DEMO_AI_ENABLED:
    st.warning(
        "Gemma runs on this Render service. Only fictional sample records are "
        "available here; the selected record's device and complaint details are "
        "sent to the hosted model and the result is not saved. Never use real "
        "customer information in this public demo.",
        title="Hosted AI demo",
    )
    if st.button("Generate a sample intake checklist", type="primary"):
        with st.spinner(f"Waiting for {OLLAMA_MODEL} on the Render CPU service..."):
            try:
                analysis = analyze_complaint(
                    job,
                    base_url=OLLAMA_BASE_URL,
                    model=OLLAMA_MODEL,
                    timeout=300,
                )
            except ModelCallError as exc:
                st.error(exc.message, title="Gemma analysis unavailable")
            else:
                st.subheader("AI intake suggestions · unconfirmed")
                st.write(analysis.complaint_summary)
                for title, items in (
                    ("Reported symptoms", analysis.reported_symptoms),
                    ("Information to collect", analysis.missing_information),
                    ("Follow-up questions", analysis.follow_up_questions),
                    ("Preliminary checklist", analysis.diagnostic_checklist),
                    ("Safe inspection steps", analysis.safe_inspection_steps),
                ):
                    st.markdown(f"**{title}**")
                    if items:
                        for item in items:
                            st.write(f"- {item}")
                    else:
                        st.write("None identified.")
                st.markdown("**Possible explanations · not diagnoses**")
                if analysis.possible_explanations:
                    for item in analysis.possible_explanations:
                        st.write(f"- {item.explanation} (unconfirmed)")
                else:
                    st.write("None identified.")
                st.caption("Review suggestions; they are not a diagnosis.")
else:
    st.info(
        "Hosted AI is disabled. Set REPAIRDESK_DEMO_AI=true and configure "
        "OLLAMA_BASE_URL and OLLAMA_MODEL to enable the fictional sample analysis."
    )
