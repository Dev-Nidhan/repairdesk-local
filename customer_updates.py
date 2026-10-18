"""Offline customer-update text built only from the repair record and confirmed notes."""

from __future__ import annotations

import re

from schemas import JOB_STATUS_LABELS

_CONFIRMED_FAULT = re.compile(r"(?i)confirmed (hardware|fault)|fault is confirmed|hardware fault is confirmed")
_UNSENT_LINE = "This message was prepared in the shop. It has not been sent."


def default_next_step(status: str) -> str:
    if status == "awaiting_inspection":
        return "We will inspect the device and contact you before any paid work."
    if status == "in_progress":
        return "The repair is in progress. We will send another update when there is something new to confirm."
    if status == "completed":
        return "The job is marked complete in our records. Contact the shop if you still need help with this device."
    return "We will update you when the next confirmed step is ready."


def build_customer_update(job: dict, confirmed_notes: str = "", next_step: str = "") -> str:
    name = (job.get("customer_name") or "").strip() or (job.get("customer_reference") or "").strip() or "there"
    confirmed = confirmed_notes.strip() or "None beyond the repair record."
    step = next_step.strip() or default_next_step(str(job.get("status", "")))
    damage = (job.get("visible_damage") or "").strip() or "None recorded."
    accessories = (job.get("accessories") or "").strip() or "None recorded."
    status = JOB_STATUS_LABELS.get(job.get("status", ""), str(job.get("status", "")))
    lines = [
        f"Hello {name},",
        "",
        f"This is an update from the shop about repair {job['id']}.",
        "",
        f"Device: {job['brand']} {job['model']} ({job['device_category']})",
        f"Status: {status}",
        "",
        "What you reported:",
        (job.get("complaint") or "").strip(),
        "",
        "What we have noted so far:",
        f"- Visible damage: {damage}",
        f"- Accessories received: {accessories}",
        "",
        "Technician-confirmed notes:",
        confirmed,
        "",
        "Next step:",
        step,
        "",
        "These notes describe the current record only. They are not a confirmed diagnosis.",
        "",
        _UNSENT_LINE,
    ]
    return "\n".join(lines)


def ensure_unsent_footer(message: str) -> str:
    text = message.strip()
    if "has not been sent" not in text.lower():
        text = f"{text}\n\n{_UNSENT_LINE}"
    return text


def diagnosis_warning(message: str) -> str | None:
    if _CONFIRMED_FAULT.search(message):
        return (
            "This draft sounds like a confirmed diagnosis. Edit it before you share it. "
            "The model cannot confirm a hardware fault."
        )
    return None
