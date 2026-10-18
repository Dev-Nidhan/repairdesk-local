"""RepairDesk Local: shop records first, local model second."""

from __future__ import annotations

import hashlib
import html
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

from ai_service import (
    ModelAvailability,
    ModelCallError,
    analyze_complaint,
    check_model,
    draft_customer_message,
)
from customer_updates import build_customer_update, diagnosis_warning
from database import Database
from demo_data import load_demo_data
from estimates import display_currency, format_cents, format_quantity
from schemas import (
    DEVICE_CATEGORIES,
    ESTIMATE_STATUS_LABELS,
    JOB_STATUSES,
    JOB_STATUS_LABELS,
    ComplaintAnalysis,
    credential_warning,
)

APP_DIR = Path(__file__).resolve().parent
APP_VERSION = "1.0"

NAV_ITEMS = (
    ("Dashboard", "Dashboard", ":material/space_dashboard:"),
    ("Repair jobs", "Repair jobs", ":material/handyman:"),
    ("New job", "New repair", ":material/add_circle:"),
    ("Estimates", "Estimates", ":material/receipt_long:"),
    ("Settings", "Settings", ":material/settings:"),
)

_CSS = """
<style>
div[data-testid="stMetric"] {
  background: #ffffff;
  border: 1px solid #e3e8ee;
  border-radius: 10px;
  padding: 0.85rem 1rem 0.7rem 1rem;
  box-shadow: 0 1px 2px rgba(15, 39, 68, 0.05);
}
div[data-testid="stMetric"] label {
  color: #526277;
}
.rd-brand {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  margin: 0.15rem 0 0.45rem 0;
}
div[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:has(> div:nth-child(4) [data-testid="stMetric"]) > div:nth-child(1) [data-testid="stMetric"] {
  box-shadow: inset 3px 0 0 #64748b;
}
div[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:has(> div:nth-child(4) [data-testid="stMetric"]) > div:nth-child(2) [data-testid="stMetric"] {
  box-shadow: inset 3px 0 0 #d97706;
}
div[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:has(> div:nth-child(4) [data-testid="stMetric"]) > div:nth-child(3) [data-testid="stMetric"] {
  box-shadow: inset 3px 0 0 #0f766e;
}
div[data-testid="stMain"] div[data-testid="stHorizontalBlock"]:has(> div:nth-child(4) [data-testid="stMetric"]) > div:nth-child(4) [data-testid="stMetric"] {
  box-shadow: inset 3px 0 0 #15803d;
}
.rd-logo {
  width: 2.1rem;
  height: 2.1rem;
  border-radius: 8px;
  background: #0f766e;
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.rd-name {
  font-weight: 700;
  font-size: 1.02rem;
  line-height: 1.2;
}
.rd-sub {
  font-size: 0.78rem;
  opacity: 0.78;
  margin-top: 0.1rem;
}
[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {
  background-color: #121C45 !important;
}
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"],
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] {
  justify-content: flex-start !important;
  text-align: left !important;
  padding-left: 16px !important;
  gap: 0.7rem !important;
  font-weight: 500 !important;
}
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] p,
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] p {
  font-weight: 500 !important;
}
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] > div,
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] > div {
  justify-content: flex-start !important;
  width: 100% !important;
}
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] {
  background: transparent !important;
  border-color: transparent !important;
  color: #f4f7fb !important;
  box-shadow: none !important;
}
[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"]:hover {
  background: rgba(255, 255, 255, 0.1) !important;
  border-color: transparent !important;
  color: #ffffff !important;
}
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] {
  background: rgba(255, 255, 255, 0.16) !important;
  border-color: transparent !important;
  color: #ffffff !important;
  box-shadow: none !important;
}
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:hover {
  background: rgba(255, 255, 255, 0.22) !important;
  border-color: transparent !important;
  color: #ffffff !important;
}
.status-pill {
  display: inline-block;
  padding: 0.12rem 0.5rem;
  border-radius: 6px;
  font-size: 0.82rem;
  font-weight: 650;
  border: 1px solid transparent;
}
.status-awaiting_inspection { background: #fff4d6; color: #7a4e00; border-color: #f3e0a2; }
.status-in_progress { background: #e7f6f4; color: #0f5c56; border-color: #c5e7e2; }
.status-completed { background: #e8f6ee; color: #146c43; border-color: #c6e8d4; }
.status-draft { background: #eef1f4; color: #334155; border-color: #dde3ea; }
.status-approved { background: #e8f6ee; color: #146c43; border-color: #c6e8d4; }
.status-declined { background: #fdecec; color: #9f1239; border-color: #f6d0d0; }
.model-ready { color: #ffffff; font-weight: 700; }
.model-model_missing { color: #ffe08a; font-weight: 650; }
.model-unreachable { color: #ffc9c9; font-weight: 650; }
.section-label {
  margin: 0.4rem 0 0.15rem 0;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #526277;
}
.rd-section {
  margin-top: 1.05rem;
}
.rd-meta {
  margin: 0.1rem 0 0.45rem 0;
  color: #122033;
  line-height: 1.35;
  overflow-wrap: anywhere;
}
.rd-meta span {
  display: block;
  margin-bottom: 0.05rem;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #526277;
}
.rd-issue {
  margin: 0.2rem 0 0.1rem 0;
  color: #334155;
}
.rd-cell {
  margin: 0.1rem 0 0.35rem 0;
}
.rd-device {
  margin: 0.1rem 0 0.15rem 0;
  font-size: 1.2rem;
  font-weight: 650;
  line-height: 1.35;
  color: #122033;
  overflow-wrap: anywhere;
}
.rd-pill-wrap {
  margin-top: 0.85rem;
}
.status-reported { background: #eef1f4; color: #334155; border-color: #dde3ea; }
.status-checks { background: #e7f6f4; color: #0f5c56; border-color: #c5e7e2; }
.status-hypothesis { background: #fff4d6; color: #7a4e00; border-color: #f3e0a2; }
.status-confirmed { background: #e8f6ee; color: #146c43; border-color: #c6e8d4; }
</style>
"""


def load_settings() -> dict:
    load_dotenv(APP_DIR / ".env")
    db_raw = os.getenv("REPAIRDESK_DB_PATH", "repairdesk.db")
    db_path = Path(db_raw)
    if not db_path.is_absolute():
        db_path = APP_DIR / db_path
    currency = display_currency(os.getenv("REPAIRDESK_CURRENCY"), db_path.exists() and db_path.stat().st_size > 0)
    return {
        "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/"),
        "ollama_model": os.getenv("OLLAMA_MODEL", "gemma3:4b").strip() or "gemma3:4b",
        "db_path": db_path,
        "currency": currency,
    }


@st.cache_resource
def get_database(path: str) -> Database:
    return Database(path)


@st.cache_data(ttl=20, show_spinner=False)
def cached_model_status(base_url: str, model: str) -> str:
    return check_model(base_url, model).value


def init_state() -> None:
    st.session_state.setdefault("page", "Dashboard")
    st.session_state.setdefault("job_id", None)
    st.session_state.setdefault("confirm_demo", False)
    st.session_state.setdefault("flash_success", None)
    st.session_state.setdefault("flash_warning", None)


def show_flashes() -> None:
    if st.session_state.flash_success:
        st.toast(st.session_state.flash_success)
        st.success(st.session_state.flash_success)
        st.session_state.flash_success = None
    if st.session_state.flash_warning:
        st.warning(st.session_state.flash_warning)
        st.session_state.flash_warning = None


def go_to(page: str) -> None:
    st.session_state.page = page
    st.rerun()


def open_job(job_id: str, section: str | None = None) -> None:
    st.session_state.job_id = job_id
    st.session_state.page = "Job"
    if section:
        st.session_state[f"section-{job_id}"] = section
    st.rerun()


def customer_label(job: dict) -> str:
    return job["customer_name"] or job["customer_reference"] or "Unnamed customer"


def device_label(job: dict) -> str:
    return f"{job['brand']} {job['model']}".strip()


def money(cents: int, currency: str) -> str:
    return f"{currency} {format_cents(cents)}"


def short_when(value: str | None) -> str:
    if not value:
        return "Not recorded"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value.replace("T", " ")[:16]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().strftime("%d %b %Y, %H:%M")


def clip_label(text: str, limit: int = 42) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def greeting() -> str:
    hour = datetime.now().hour
    if hour < 12:
        return "Good morning"
    if hour < 17:
        return "Good afternoon"
    return "Good evening"


def status_pill(status: str, labels: dict[str, str] | None = None) -> str:
    names = labels or JOB_STATUS_LABELS
    label = html.escape(names.get(status, status))
    safe_status = html.escape(status)
    return f'<span class="status-pill status-{safe_status}">{label}</span>'


def job_fields_from_inputs(
    customer_name: str,
    customer_reference: str,
    device_category: str,
    brand: str,
    model: str,
    complaint: str,
    visible_damage: str,
    accessories: str,
    technician_notes: str,
) -> dict:
    return {
        "customer_name": customer_name,
        "customer_reference": customer_reference,
        "device_category": device_category,
        "brand": brand,
        "model": model,
        "complaint": complaint,
        "visible_damage": visible_damage,
        "accessories": accessories,
        "technician_notes": technician_notes,
    }


def filter_jobs(jobs: list[dict], category: str) -> list[dict]:
    if category == "Any":
        return jobs
    return [job for job in jobs if job["device_category"] == category]


def page_header(title: str, subtitle: str, action_label: str | None = None, action_page: str | None = None) -> None:
    left, right = st.columns([5, 1.3])
    left.markdown(f"## {title}")
    left.caption(subtitle)
    if action_label and action_page and right.button(action_label, type="primary", width="stretch"):
        go_to(action_page)


def section_label(text: str) -> None:
    st.markdown(f'<p class="section-label">{html.escape(text)}</p>', unsafe_allow_html=True)


def detail_section(text: str) -> None:
    st.markdown(f'<p class="section-label rd-section">{html.escape(text)}</p>', unsafe_allow_html=True)


def _show_field(label: str, value: str | None, empty: str = "None recorded.") -> None:
    st.caption(label)
    text = (value or "").strip()
    st.write(text if text else empty)


def _meta(label: str, value: str | None, empty: str = "None recorded.") -> None:
    text = (value or "").strip() or empty
    st.markdown(
        f'<p class="rd-meta"><span>{html.escape(label)}</span>{html.escape(text)}</p>',
        unsafe_allow_html=True,
    )


def _cell(column, text: str, align: str = "left") -> None:
    column.markdown(
        f'<p class="rd-cell" style="text-align:{align}">{html.escape(text)}</p>',
        unsafe_allow_html=True,
    )


def _kind_tag(label: str, kind: str) -> None:
    st.markdown(
        f'<span class="status-pill status-{html.escape(kind)}">{html.escape(label)}</span>',
        unsafe_allow_html=True,
    )


def current_model_status(settings: dict) -> ModelAvailability:
    return ModelAvailability(cached_model_status(settings["ollama_base_url"], settings["ollama_model"]))


def render_sidebar(settings: dict) -> None:
    status = current_model_status(settings)
    page = st.session_state.page
    active = "Repair jobs" if page == "Job" else page
    with st.sidebar:
        st.markdown(
            """
            <div class="rd-brand">
              <div class="rd-logo">RD</div>
              <div>
                <div class="rd-name">RepairDesk Local</div>
                <div class="rd-sub">Local Repair Management</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        for page_id, label, icon in NAV_ITEMS:
            if st.button(
                label,
                key=f"nav-{page_id}",
                icon=icon,
                width="stretch",
                type="primary" if active == page_id else "secondary",
            ):
                go_to(page_id)
        if page == "Job" and st.session_state.job_id:
            st.caption(f"Open {st.session_state.job_id}")
        st.divider()
        st.caption("Local AI")
        st.markdown(
            f'<p class="model-{status.value}">{html.escape(_model_label(status, settings["ollama_model"]))}</p>',
            unsafe_allow_html=True,
        )
        st.caption("On this computer only. Records work without the model.")
        if st.button("Check model", icon=":material/memory:", width="stretch", key="sidebar-check-model"):
            cached_model_status.clear()
            st.rerun()
        st.caption(f"Version {APP_VERSION} · No cloud sync")


def _model_label(status: ModelAvailability, model: str) -> str:
    if status == ModelAvailability.READY:
        return f"Local model ready · {model}"
    if status == ModelAvailability.MODEL_MISSING:
        return f"{model} is not downloaded"
    return "Ollama is not reachable"


def render_dashboard(db: Database) -> None:
    page_header(
        greeting(),
        "Jobs on this computer, from intake through completion.",
        "New repair",
        "New job",
    )
    show_flashes()
    counts = db.counts()
    total, waiting, active, done = st.columns(4)
    total.metric("Total repair jobs", counts["total"], border=True, icon=":material/list_alt:")
    waiting.metric("Awaiting inspection", counts["awaiting_inspection"], border=True, icon=":material/schedule:")
    active.metric("In progress", counts["in_progress"], border=True, icon=":material/build:")
    done.metric("Completed", counts["completed"], border=True, icon=":material/check_circle:")
    recent = db.recent()
    attention = db.search(status="awaiting_inspection")
    if not recent:
        st.info("No repair jobs yet. Create the first job when a device arrives.")
        if st.button("Create the first repair", type="primary"):
            go_to("New job")
    elif attention:
        jobs_col, attention_col = st.columns([1.8, 1], gap="large")
        with jobs_col:
            st.markdown("### Recent repair jobs")
            _job_table(recent, key_prefix="dash", date_field="created_at", date_label="Created")
        with attention_col:
            st.markdown("### Needs attention")
            st.caption(f"{len(attention)} awaiting inspection")
            for job in attention[:6]:
                label = f"{job['id']} · {clip_label(customer_label(job), 24)}"
                if st.button(label, key=f"attention-{job['id']}", width="stretch"):
                    open_job(job["id"], "Record")
            if len(attention) > 6:
                st.caption(f"{len(attention) - 6} more in Repair jobs.")
    else:
        st.markdown("### Recent repair jobs")
        _job_table(recent, key_prefix="dash", date_field="created_at", date_label="Created")
    with st.expander("Sample records"):
        st.caption("Fictional jobs are added only after you confirm. They are never loaded at startup.")
        if st.button("Load sample jobs"):
            st.session_state.confirm_demo = True
        if st.session_state.confirm_demo:
            st.warning("This adds three fictional repair jobs to the local database.")
            yes, no = st.columns(2)
            if yes.button("Add fictional sample jobs", type="primary"):
                added = load_demo_data(db)
                st.session_state.confirm_demo = False
                if added:
                    st.session_state.flash_success = (
                        f"Added {added} fictional sample job{'s' if added != 1 else ''}."
                    )
                else:
                    st.session_state.flash_success = "Sample jobs are already loaded."
                st.rerun()
            if no.button("Cancel"):
                st.session_state.confirm_demo = False
                st.rerun()


def render_new_job(db: Database) -> None:
    page_header("New repair", "Take in a device. Passwords and PINs do not belong in this record.")
    show_flashes()
    with st.form("new-job", clear_on_submit=False):
        section_label("Customer")
        name_col, ref_col = st.columns(2)
        customer_name = name_col.text_input("Customer name", help="Required if you leave the reference blank.")
        customer_reference = ref_col.text_input(
            "Customer reference",
            help="Optional when a name is entered. Use either a name or a reference.",
        )
        section_label("Device")
        device_category = st.selectbox("Device category *", DEVICE_CATEGORIES)
        brand_col, model_col = st.columns(2)
        brand = brand_col.text_input("Brand *")
        model = model_col.text_input("Model *")
        section_label("Reported problem")
        complaint = st.text_area("Customer's complaint *", height=110)
        section_label("Condition and accessories")
        damage_col, accessory_col = st.columns(2)
        visible_damage = damage_col.text_area("Visible damage", height=90)
        accessories = accessory_col.text_area("Accessories received", height=90)
        section_label("Technician notes")
        technician_notes = st.text_area(
            "Technician notes",
            height=90,
            help="Shop notes only. Do not store passwords, PINs, or unlock codes.",
        )
        submitted = st.form_submit_button("Create repair job", type="primary")
    if not submitted:
        return
    fields = job_fields_from_inputs(
        customer_name,
        customer_reference,
        device_category,
        brand,
        model,
        complaint,
        visible_damage,
        accessories,
        technician_notes,
    )
    try:
        job_id = db.create_job(fields)
    except ValueError as exc:
        st.error(str(exc))
        return
    warning = credential_warning(fields)
    st.session_state.flash_success = f"Created {job_id}. Review the record, then inspect the device."
    if warning:
        st.session_state.flash_warning = warning
    open_job(job_id, "Record")


def render_jobs(db: Database) -> None:
    page_header(
        "Repair jobs",
        "Search the jobs stored on this computer.",
        "New repair",
        "New job",
    )
    show_flashes()
    query = st.text_input("Search", placeholder="Repair ID, customer, brand, model, or complaint")
    status_col, category_col = st.columns(2)
    status = status_col.selectbox(
        "Status",
        ("Any", *JOB_STATUSES),
        format_func=lambda value: "Any status" if value == "Any" else JOB_STATUS_LABELS[value],
    )
    category = category_col.selectbox(
        "Device category",
        ("Any", *DEVICE_CATEGORIES),
        format_func=lambda value: "Any category" if value == "Any" else value.capitalize(),
    )
    jobs = filter_jobs(db.search(query, None if status == "Any" else status), category)
    filtered = bool(query.strip() or status != "Any" or category != "Any")
    if not jobs:
        if filtered:
            st.info("No repair jobs match those filters.")
        else:
            st.info("No repair jobs yet. Create one when a device arrives.")
            if st.button("New repair", type="primary", key="jobs-empty-new"):
                go_to("New job")
        return
    st.caption(f"{len(jobs)} job{'s' if len(jobs) != 1 else ''}")
    _job_table(jobs, key_prefix="list", date_field="created_at", date_label="Created")


def _job_table(jobs: list[dict], key_prefix: str, date_field: str, date_label: str) -> None:
    frame = pd.DataFrame(
        [
            {
                "Repair": job["id"],
                "Customer": clip_label(customer_label(job)),
                "Device": clip_label(device_label(job)),
                "Category": job["device_category"].capitalize(),
                "Status": JOB_STATUS_LABELS[job["status"]],
                date_label: short_when(job.get(date_field)),
            }
            for job in jobs
        ]
    )
    styled = frame.style.map(_status_cell_style, subset=["Status"])
    state = st.dataframe(
        styled,
        width="stretch",
        hide_index=True,
        row_height=40,
        on_select="rerun",
        selection_mode="single-row",
        key=f"{key_prefix}-table",
        column_config={
            "Repair": st.column_config.TextColumn("Repair", width="small"),
            "Customer": st.column_config.TextColumn("Customer", width="medium"),
            "Device": st.column_config.TextColumn("Device", width="medium"),
            "Category": st.column_config.TextColumn("Category", width="small"),
            "Status": st.column_config.TextColumn("Status", width="medium"),
            date_label: st.column_config.TextColumn(date_label, width="medium"),
        },
    )
    st.caption("Select a row to open that repair.")
    _follow_row_selection([job["id"] for job in jobs], state, key_prefix, "Record")


_STATUS_CELL_STYLE = {
    "Awaiting inspection": "background-color: #fff4d6; color: #7a4e00",
    "In progress": "background-color: #e7f6f4; color: #0f5c56",
    "Completed": "background-color: #e8f6ee; color: #146c43",
}


def _status_cell_style(value: str) -> str:
    return _STATUS_CELL_STYLE.get(value, "")


def _follow_row_selection(record_ids: list[str], state, key_prefix: str, section: str) -> None:
    selected = list(state.selection.rows)
    marker = f"{key_prefix}-selected-id"
    if not selected:
        st.session_state[marker] = None
        return
    index = selected[0]
    if index >= len(record_ids):
        return
    job_id = record_ids[index]
    if st.session_state.get(marker) == job_id:
        return
    st.session_state[marker] = job_id
    open_job(job_id, section)


def render_estimates(db: Database, settings: dict) -> None:
    page_header(
        "Estimates",
        "Prices are entered by the shop. Nothing here is approved until you say so.",
        "New repair",
        "New job",
    )
    show_flashes()
    jobs = db.search()
    if not jobs:
        st.info("No repair jobs yet, so there are no estimates.")
        if st.button("New repair", type="primary", key="estimates-empty-new"):
            go_to("New job")
        return
    rows = []
    for job in jobs:
        estimate = db.get_estimate(job["id"])
        rows.append((job, estimate))
    frame = pd.DataFrame(
        [
            {
                "Repair": job["id"],
                "Customer": clip_label(customer_label(job)),
                "Device": clip_label(device_label(job)),
                "Estimate": ESTIMATE_STATUS_LABELS[estimate["status"]] if estimate else "No estimate",
                "Total": money(estimate["total_cents"], settings["currency"]) if estimate else "—",
                "Updated": short_when(estimate["updated_at"]) if estimate else "—",
            }
            for job, estimate in rows
        ]
    )
    state = st.dataframe(
        frame,
        width="stretch",
        hide_index=True,
        row_height=40,
        on_select="rerun",
        selection_mode="single-row",
        key="estimates-table",
        column_config={
            "Repair": st.column_config.TextColumn("Repair", width="small"),
            "Customer": st.column_config.TextColumn("Customer", width="medium"),
            "Device": st.column_config.TextColumn("Device", width="medium"),
            "Estimate": st.column_config.TextColumn("Estimate", width="small"),
            "Total": st.column_config.TextColumn("Total", width="small"),
            "Updated": st.column_config.TextColumn("Updated", width="medium"),
        },
    )
    st.caption("Select a row to open that estimate.")
    _follow_row_selection([job["id"] for job, _estimate in rows], state, "estimates", "Estimate")


def render_settings(settings: dict) -> None:
    page_header("Settings", "Local model status and where this shop's records live.")
    show_flashes()
    status = current_model_status(settings)
    with st.container(border=True):
        st.markdown("**Local model**")
        st.markdown(status_pill(_model_status_key(status), _model_status_labels()) , unsafe_allow_html=True)
        st.write(_model_label(status, settings["ollama_model"]))
        st.caption(f"Configured model: {settings['ollama_model']}")
        st.caption(f"Ollama address: {settings['ollama_base_url']}")
        if status != ModelAvailability.READY:
            st.info(
                "Job records, estimates, and template updates keep working. "
                f"Complaint analysis needs Ollama and a downloaded model: ollama pull {settings['ollama_model']}. "
                "Downloading the model needs a network connection once. Later use of that model stays on this computer."
            )
        if st.button("Check model again", type="primary"):
            cached_model_status.clear()
            st.rerun()
    with st.container(border=True):
        st.markdown("**Privacy**")
        st.write(
            "Repair records stay in the SQLite file on this computer. "
            "The app does not sync them, send analytics, or call a cloud AI service. "
            "When you ask for an analysis, the complaint and device details go to the local Ollama address only."
        )
        st.caption(f"Database file: {settings['db_path'].name}")
        st.caption(
            f"Currency label: {settings['currency']}. "
            "Amounts stay as the numbers you typed. This label does not convert them. "
            "A new database with no currency setting uses INR. An existing database stays USD "
            "unless REPAIRDESK_CURRENCY is set."
        )


def _model_status_key(status: ModelAvailability) -> str:
    if status == ModelAvailability.READY:
        return "approved"
    if status == ModelAvailability.MODEL_MISSING:
        return "awaiting_inspection"
    return "declined"


def _model_status_labels() -> dict[str, str]:
    return {
        "approved": "Ready",
        "awaiting_inspection": "Model missing",
        "declined": "Unreachable",
    }


def render_job(db: Database, settings: dict) -> None:
    show_flashes()
    job = db.get_job(st.session_state.job_id or "")
    if job is None:
        page_header("Repair", "Choose a repair job to see its record.")
        st.info("That repair is not in the local database.")
        missing_jobs, missing_dash, _missing_space = st.columns([1.45, 1.15, 3])
        if missing_jobs.button("Back to repair jobs", icon=":material/arrow_back:"):
            go_to("Repair jobs")
        if missing_dash.button("Dashboard", icon=":material/space_dashboard:"):
            go_to("Dashboard")
        return
    _render_job_header(job)
    warning = credential_warning(job)
    if warning:
        st.warning(warning)
    _render_record(db, job)
    _render_assistant(db, job, settings)
    _render_estimate(db, job, settings["currency"])
    _render_update(db, job, settings)


def _render_job_header(job: dict) -> None:
    jobs_col, dash_col, _space = st.columns([1.45, 1.15, 3])
    if jobs_col.button(
        "Back to repair jobs",
        icon=":material/arrow_back:",
        key=f"back-jobs-{job['id']}",
        width="stretch",
    ):
        go_to("Repair jobs")
    if dash_col.button(
        "Dashboard",
        icon=":material/space_dashboard:",
        key=f"back-dash-{job['id']}",
        width="stretch",
    ):
        go_to("Dashboard")
    title_col, pill_col = st.columns([5, 1.35])
    title_col.markdown(f"## {html.escape(job['id'])}")
    title_col.markdown(
        f'<p class="rd-device">{html.escape(device_label(job))}</p>',
        unsafe_allow_html=True,
    )
    title_col.caption(
        f"{customer_label(job)} · {job['device_category'].replace('_', ' ').title()}"
    )
    pill_col.markdown(
        f'<div class="rd-pill-wrap">{status_pill(job["status"])}</div>',
        unsafe_allow_html=True,
    )
    timing = f"Created {short_when(job['created_at'])} · Updated {short_when(job['updated_at'])}"
    if job["completed_at"]:
        timing += f" · Completed {short_when(job['completed_at'])}"
    if job["reopened_at"]:
        timing += f" · Reopened {short_when(job['reopened_at'])}"
    st.caption(timing)
    issue = (job["complaint"] or "").strip()
    summary = clip_label(issue, 140) if issue else "No complaint recorded."
    st.markdown(f'<p class="rd-issue">Reported: {html.escape(summary)}</p>', unsafe_allow_html=True)


def _apply_job_status(db: Database, job: dict, choice: str) -> None:
    try:
        db.set_status(job["id"], choice)
    except ValueError as exc:
        st.error(str(exc))
        return
    st.session_state.pop(f"pending-complete-{job['id']}", None)
    st.session_state.pop(f"status-same-{job['id']}", None)
    st.session_state.flash_success = f"{job['id']} is now {JOB_STATUS_LABELS[choice].lower()}."
    st.rerun()


def _render_status_controls(db: Database, job: dict) -> None:
    job_id = job["id"]
    complete_key = f"pending-complete-{job_id}"
    reopen_key = f"pending-reopen-{job_id}"
    if job["status"] == "completed":
        st.caption(f"Completed {short_when(job['completed_at'])}. Reopen the job before changing its status.")
        reopen_col, button_col = st.columns([2.2, 1])
        target = reopen_col.selectbox(
            "Reopen as",
            ("in_progress", "awaiting_inspection"),
            format_func=lambda value: JOB_STATUS_LABELS[value],
            key=f"reopen-{job_id}",
        )
        if button_col.button("Reopen job", key=f"reopen-btn-{job_id}", width="stretch"):
            st.session_state[reopen_key] = target
            st.rerun()
        pending = st.session_state.get(reopen_key)
        if pending in {"in_progress", "awaiting_inspection"}:
            with st.container(border=True):
                st.warning(
                    f"Reopen {job_id} as {JOB_STATUS_LABELS[pending]}? "
                    "The job returns to the working list."
                )
                yes_col, no_col = st.columns(2)
                if yes_col.button("Confirm reopen", key=f"confirm-reopen-{job_id}", type="primary"):
                    try:
                        db.reopen_job(job_id, pending)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.pop(reopen_key, None)
                        st.session_state.flash_success = f"{job_id} is open again."
                        st.rerun()
                if no_col.button("Cancel", key=f"cancel-reopen-{job_id}"):
                    st.session_state.pop(reopen_key, None)
                    st.rerun()
        return
    st.caption("The only statuses are awaiting inspection, in progress, and completed.")
    status_col, button_col = st.columns([2.2, 1])
    choice = status_col.selectbox(
        "Status",
        JOB_STATUSES,
        index=JOB_STATUSES.index(job["status"]),
        format_func=lambda value: JOB_STATUS_LABELS[value],
        key=f"status-{job_id}-{job['status']}",
    )
    if button_col.button("Update status", key=f"status-btn-{job_id}", width="stretch"):
        if choice == job["status"]:
            st.session_state[f"status-same-{job_id}"] = True
            st.session_state.pop(complete_key, None)
            st.rerun()
        if choice == "completed":
            st.session_state[complete_key] = True
            st.session_state.pop(f"status-same-{job_id}", None)
            st.rerun()
        st.session_state.pop(complete_key, None)
        st.session_state.pop(f"status-same-{job_id}", None)
        _apply_job_status(db, job, choice)
    if st.session_state.get(f"status-same-{job_id}"):
        st.caption(f"{job_id} is already {JOB_STATUS_LABELS[job['status']].lower()}.")
    if st.session_state.get(complete_key):
        with st.container(border=True):
            st.warning(
                f"Mark {job_id} completed? This records a completion time. "
                "You can reopen the job later if work continues."
            )
            yes_col, no_col = st.columns(2)
            if yes_col.button("Confirm completion", key=f"confirm-complete-{job_id}", type="primary"):
                _apply_job_status(db, job, "completed")
            if no_col.button("Cancel", key=f"cancel-complete-{job_id}"):
                st.session_state.pop(complete_key, None)
                st.rerun()


def _render_record(db: Database, job: dict) -> None:
    detail_section("Repair record")
    info_col, problem_col = st.columns(2)
    with info_col:
        section_label("Customer and device")
        with st.container(border=True):
            name_col, ref_col = st.columns(2)
            with name_col:
                _meta("Customer name", job["customer_name"])
            with ref_col:
                _meta("Customer reference", job["customer_reference"])
            category_col, device_col = st.columns(2)
            with category_col:
                _meta("Category", job["device_category"].replace("_", " ").title())
            with device_col:
                _meta("Brand and model", device_label(job))
        section_label("Accessories received")
        with st.container(border=True):
            _meta("With the device", job["accessories"])
    with problem_col:
        section_label("Reported complaint and visible damage")
        with st.container(border=True):
            _meta("Customer complaint", job["complaint"], "No complaint recorded.")
            _meta("Visible damage", job["visible_damage"])
        section_label("Technician notes")
        with st.container(border=True):
            _meta("Shop notes", job["technician_notes"])
            st.caption("Written by you. These are not model output.")
    with st.expander("Edit record", expanded=False):
        st.caption("Do not enter passwords, PINs, or other device credentials.")
        with st.form(f"edit-{job['id']}"):
            section_label("Customer")
            name_col, ref_col = st.columns(2)
            customer_name = name_col.text_input("Customer name", value=job["customer_name"])
            customer_reference = ref_col.text_input("Customer reference", value=job["customer_reference"])
            section_label("Device")
            device_category = st.selectbox(
                "Device category *",
                DEVICE_CATEGORIES,
                index=DEVICE_CATEGORIES.index(job["device_category"]),
            )
            brand_col, model_col = st.columns(2)
            brand = brand_col.text_input("Brand *", value=job["brand"])
            model = model_col.text_input("Model *", value=job["model"])
            section_label("Reported problem")
            complaint = st.text_area("Customer's complaint *", value=job["complaint"])
            section_label("Condition and accessories")
            damage_col, accessory_col = st.columns(2)
            visible_damage = damage_col.text_area("Visible damage", value=job["visible_damage"])
            accessories = accessory_col.text_area("Accessories received", value=job["accessories"])
            section_label("Technician notes")
            technician_notes = st.text_area("Technician notes", value=job["technician_notes"])
            submitted = st.form_submit_button("Save record", type="primary")
    if not submitted:
        return
    fields = job_fields_from_inputs(
        customer_name,
        customer_reference,
        device_category,
        brand,
        model,
        complaint,
        visible_damage,
        accessories,
        technician_notes,
    )
    try:
        db.update_job(job["id"], fields)
    except ValueError as exc:
        st.error(str(exc))
        return
    st.session_state.flash_success = f"Saved {job['id']}."
    warning = credential_warning(fields)
    if warning:
        st.session_state.flash_warning = warning
    st.rerun()


def _render_assistant(db: Database, job: dict, settings: dict) -> None:
    detail_section("AI-assisted preliminary analysis")
    st.caption(
        "Analyze complaint runs only when you press the button. "
        "Reported symptoms come from the customer. Hypotheses are unconfirmed. "
        "Technician-confirmed findings are only what you write in the update below."
    )
    status = current_model_status(settings)
    error_key = f"analysis-error-{job['id']}"
    with st.container(border=True):
        model_col, action_col = st.columns([2.4, 1.2])
        model_col.write(_model_label(status, settings["ollama_model"]))
        model_col.caption(
            "The model has not confirmed a hardware fault. "
            "Skip live-mains work, battery puncture, and bypassing a safety device."
        )
        failed = bool(st.session_state.get(error_key))
        label = "Try analysis again" if failed else "Analyze complaint"
        if action_col.button(label, type="primary", key=f"analyze-{job['id']}", width="stretch"):
            with st.spinner("Reading the complaint with the local model. This can take a minute."):
                try:
                    analysis = analyze_complaint(
                        job,
                        base_url=settings["ollama_base_url"],
                        model=settings["ollama_model"],
                    )
                except ModelCallError as exc:
                    st.session_state[error_key] = exc.message
                else:
                    try:
                        if not isinstance(analysis, ComplaintAnalysis):
                            payload = analysis.model_dump() if hasattr(analysis, "model_dump") else analysis
                            analysis = ComplaintAnalysis.model_validate(payload)
                        db.save_analysis(job["id"], settings["ollama_model"], analysis)
                    except (TypeError, ValidationError, ValueError) as exc:
                        st.session_state[error_key] = (
                            "The local model replied, but that reply could not be saved. "
                            "Nothing was saved. "
                            + str(exc)
                        )
                    else:
                        st.session_state.pop(error_key, None)
                        st.session_state.flash_success = "Analysis saved. These notes are unconfirmed."
            st.rerun()
        if failed:
            st.error(st.session_state[error_key])
            st.caption("Nothing from that attempt was saved. Use Try analysis again when the local model is available.")
    analyses = db.list_analyses(job["id"])
    if not analyses:
        st.info("No local analysis saved for this repair. You can inspect the device without the model.")
        return
    latest = analyses[0]
    st.caption(
        f"Saved from {latest['model_name']} at {short_when(latest['created_at'])}. "
        "This is not a verified diagnosis."
    )
    reported_col, action_col = st.columns(2)
    with reported_col:
        with st.container(border=True):
            _kind_tag("From the customer's report", "reported")
            st.caption("Restated from the complaint. This is not a finding by the model.")
            _show_field("Complaint summary", latest["complaint_summary"], "None noted.")
            _bullets("Reported symptoms", latest["reported_symptoms"])
        with st.container(border=True):
            _kind_tag("Still needed from the customer", "reported")
            _bullets("Missing information", latest["missing_information"])
            _bullets("Follow-up questions", latest["follow_up_questions"])
    with action_col:
        with st.container(border=True):
            _kind_tag("Suggested checks", "checks")
            st.caption("Inspection ideas only. They do not confirm a fault.")
            _bullets("Suggested diagnostic checks", latest["diagnostic_checklist"])
            _bullets("Safe initial inspection", latest["safe_inspection_steps"])
        with st.container(border=True):
            _kind_tag("Unconfirmed hypotheses", "hypothesis")
            st.caption("Possible explanations. Not a verified diagnosis.")
            if not latest["possible_explanations"]:
                st.caption("None noted.")
            else:
                for item in latest["possible_explanations"]:
                    text = item["explanation"] if isinstance(item, dict) else str(item)
                    st.markdown(f"- {html.escape(text)}")
    if len(analyses) > 1:
        with st.expander(f"{len(analyses) - 1} earlier analysis run{'s' if len(analyses) != 2 else ''}"):
            for older in analyses[1:]:
                st.caption(f"{older['model_name']} · {short_when(older['created_at'])} · unconfirmed")
                st.write(older["complaint_summary"])


def _bullets(title: str, items: list[str]) -> None:
    st.markdown(f"**{html.escape(title)}**")
    if not items:
        st.caption("None noted.")
        return
    for item in items:
        st.markdown(f"- {html.escape(str(item))}")


def _render_estimate(db: Database, job: dict, currency: str) -> None:
    detail_section("Estimate and pricing")
    st.caption("Enter parts, labour, quantities, and prices yourself. The app does not invent prices or approvals.")
    estimate = db.get_estimate(job["id"])
    if estimate is None:
        st.info("No estimate yet for this repair.")
        if st.button("Start draft estimate", type="primary"):
            db.ensure_estimate(job["id"])
            st.rerun()
        return
    lines_col, edit_col = st.columns([1.55, 1])
    with lines_col:
        st.markdown(status_pill(estimate["status"], ESTIMATE_STATUS_LABELS), unsafe_allow_html=True)
        st.caption(
            f"Labeled {currency}. Stored numbers are not converted. "
            "Changing a line returns an approved or declined estimate to draft."
        )
        if not estimate["lines"]:
            st.info("No lines yet. Add parts and labour with the prices you want to charge.")
        else:
            with st.container(border=True):
                header = st.columns([3.2, 1, 0.8, 1.3, 1.3, 0.9])
                labels = ("Description", "Type", "Qty", "Unit price", "Line total", "")
                aligns = ("left", "left", "right", "right", "right", "left")
                for column, label, align in zip(header, labels, aligns):
                    _cell(column, label, align)
                for line in estimate["lines"]:
                    desc, kind, qty, price, total, remove = st.columns([3.2, 1, 0.8, 1.3, 1.3, 0.9])
                    _cell(desc, line["description"])
                    _cell(kind, "Part" if line["line_type"] == "part" else "Labour")
                    _cell(qty, format_quantity(line["quantity_hundredths"]), "right")
                    _cell(price, money(line["unit_price_cents"], currency), "right")
                    _cell(total, money(line["line_total_cents"], currency), "right")
                    if remove.button("Remove", key=f"remove-line-{line['id']}"):
                        db.remove_estimate_line(job["id"], line["id"])
                        st.rerun()
        with st.container(border=True):
            parts, labour, total = st.columns(3)
            parts.metric("Parts", money(estimate["parts_cents"], currency))
            labour.metric("Labour", money(estimate["labour_cents"], currency))
            total.metric("Total", money(estimate["total_cents"], currency))
        draft_col, approve_col, decline_col = st.columns(3)
        if draft_col.button("Return to draft", key=f"est-draft-{job['id']}"):
            _set_estimate_status(db, job["id"], "draft")
        if approve_col.button("Mark approved", key=f"est-approve-{job['id']}", type="primary"):
            _set_estimate_status(db, job["id"], "approved")
        if decline_col.button("Mark declined", key=f"est-decline-{job['id']}"):
            _set_estimate_status(db, job["id"], "declined")
    with edit_col:
        with st.form(f"add-line-{job['id']}"):
            section_label("Add a line")
            line_type = st.selectbox(
                "Type",
                ("part", "labour"),
                format_func=lambda value: "Part" if value == "part" else "Labour",
            )
            description = st.text_input("Description")
            quantity = st.number_input(
                "Quantity",
                min_value=0.0,
                max_value=10000.0,
                value=1.0,
                step=0.25,
                format="%.2f",
            )
            unit_price = st.number_input(
                f"Unit price ({currency})",
                min_value=0.0,
                max_value=1000000.0,
                value=0.0,
                step=0.01,
                format="%.2f",
            )
            submitted = st.form_submit_button("Add line", type="primary")
        if submitted:
            try:
                db.add_estimate_line(job["id"], line_type, description, quantity, unit_price)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.rerun()
        with st.form(f"estimate-notes-{job['id']}"):
            notes = st.text_area("Estimate notes", value=estimate["notes"], height=90)
            save_notes = st.form_submit_button("Save notes")
    if save_notes:
        try:
            db.set_estimate_notes(job["id"], notes)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()


def _set_estimate_status(db: Database, job_id: str, status: str) -> None:
    try:
        db.set_estimate_status(job_id, status)
    except (ValueError, KeyError) as exc:
        st.error(str(exc))
    else:
        st.rerun()


def _render_update(db: Database, job: dict, settings: dict) -> None:
    detail_section("Customer communication and repair progress")
    st.caption("The message is a draft prepared on this computer. Nothing is sent automatically.")
    progress_col, message_col = st.columns([1, 1.15])
    with progress_col:
        _render_status_controls(db, job)
        st.markdown("**Technician-confirmed findings**")
        st.caption(
            "Only facts you have checked belong here. "
            "Copying a hypothesis into this box is what makes it your finding."
        )
        confirmed = st.text_area(
            "Technician-confirmed facts",
            key=f"confirmed-{job['id']}",
            help="Only facts you have checked. These are separate from model suggestions.",
            height=110,
        )
        next_step = st.text_input("Next step you want to tell the customer", key=f"next-{job['id']}")
        body_key = f"update-body-{job['id']}"
        source_key = f"update-source-{job['id']}"
        if body_key not in st.session_state:
            latest = db.latest_customer_update(job["id"])
            st.session_state[body_key] = latest["body"] if latest else ""
            st.session_state[source_key] = latest["source"] if latest else "template"
        build_col, draft_col = st.columns(2)
        if build_col.button("Build update from record", type="primary"):
            st.session_state[body_key] = build_customer_update(job, confirmed, next_step)
            st.session_state[source_key] = "template"
            db.save_customer_update(job["id"], st.session_state[body_key], "template")
            st.session_state.flash_success = "Update built from the repair record. It has not been sent."
            st.rerun()
        if draft_col.button("Draft with local model"):
            template = build_customer_update(job, confirmed, next_step)
            with st.spinner("Asking the local model to rewrite this update."):
                try:
                    drafted = draft_customer_message(
                        template,
                        base_url=settings["ollama_base_url"],
                        model=settings["ollama_model"],
                    )
                except ModelCallError as exc:
                    st.error(exc.message)
                else:
                    st.session_state[body_key] = drafted
                    st.session_state[source_key] = "ollama"
                    db.save_customer_update(job["id"], drafted, "ollama")
                    st.session_state.flash_success = "Draft saved from the local model. Edit it before you copy it."
                    st.rerun()
    with message_col:
        _kind_tag("Draft · not sent", "draft")
        source = st.session_state.get(source_key, "template")
        if source == "ollama":
            st.warning(
                "This wording came from the local model. "
                "Confirmed facts are only what you typed. It has not been sent."
            )
        else:
            st.caption("Proposed wording from the repair record and your confirmed facts. It has not been sent.")
        body = st.text_area("Customer message", key=body_key, height=220)
        fault_warning = diagnosis_warning(body)
        if fault_warning:
            st.warning(fault_warning)
        save_col, copy_col = st.columns([1, 2])
        if save_col.button("Save edit", key=f"save-update-{job['id']}"):
            try:
                db.save_customer_update(job["id"], body, source if source in {"template", "ollama"} else "template")
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success("Update saved on this computer. It has not been sent.")
        with copy_col:
            if body.strip():
                _copy_button(body)
            else:
                st.caption("Build an update to copy it.")


def _copy_button(text: str) -> None:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    payload = json.dumps(text).replace("<", "\\u003c")
    st.iframe(
        f"""
        <button id="btn-{digest}" type="button"
          style="background:#0f766e;color:#ffffff;border:0;border-radius:8px;
                 padding:0.45rem 0.9rem;font-weight:650;cursor:pointer;">
          Copy update
        </button>
        <script>
          const button = document.getElementById("btn-{digest}");
          const payload = {payload};
          button.addEventListener("click", async () => {{
            let copied = false;
            try {{
              await navigator.clipboard.writeText(payload);
              copied = true;
            }} catch (err) {{
              const area = document.createElement("textarea");
              area.value = payload;
              document.body.appendChild(area);
              area.select();
              copied = document.execCommand("copy");
              area.remove();
            }}
            button.textContent = copied ? "Copied" : "Select the text and copy it";
          }});
        </script>
        """,
        height=52,
    )


def main() -> None:
    st.set_page_config(
        page_title="RepairDesk Local",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_CSS, unsafe_allow_html=True)
    init_state()
    settings = load_settings()
    db = get_database(str(settings["db_path"]))
    render_sidebar(settings)
    page = st.session_state.page
    if page == "Dashboard":
        render_dashboard(db)
    elif page == "New job":
        render_new_job(db)
    elif page == "Repair jobs":
        render_jobs(db)
    elif page == "Estimates":
        render_estimates(db, settings)
    elif page == "Settings":
        render_settings(settings)
    else:
        render_job(db, settings)


main()
