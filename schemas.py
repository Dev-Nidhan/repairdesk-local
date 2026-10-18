"""Validation models for repair jobs and local-model responses."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

DEVICE_CATEGORIES = ("laptop", "phone", "tablet", "other")
JOB_STATUSES = ("awaiting_inspection", "in_progress", "completed")
ESTIMATE_STATUSES = ("draft", "approved", "declined")
LINE_TYPES = ("part", "labour")

JOB_STATUS_LABELS = {
    "awaiting_inspection": "Awaiting inspection",
    "in_progress": "In progress",
    "completed": "Completed",
}
ESTIMATE_STATUS_LABELS = {
    "draft": "Draft",
    "approved": "Approved",
    "declined": "Declined",
}

_TEXT_LIMITS = {
    "customer_name": 200,
    "customer_reference": 200,
    "brand": 120,
    "model": 120,
    "complaint": 5000,
    "visible_damage": 5000,
    "accessories": 2000,
    "technician_notes": 5000,
}

_CREDENTIAL_PATTERN = re.compile(
    r"(?i)\b(?:password|passcode|pin\s*code|unlock\s*code)\s*[:=]"
)

_UNSAFE_STEP = re.compile(
    r"(?i)(?:"
    r"bypass(?:ing)?\s+(?:the\s+)?(?:safety|protection|fuse|thermal)"
    r"|defeat\s+(?:the\s+)?(?:safety|protection)"
    r"|live\s+mains"
    r"|puncture\s+(?:the\s+)?battery"
    r"|pry\s+open\s+the\s+battery"
    r"|short(?:ing)?\s+(?:the\s+)?battery"
    r"|bridge\s+(?:the\s+)?battery"
    r")"
)

SAFE_STEP_REPLACEMENT = (
    "Use an external check only. Do not do live-mains work, puncture a battery, "
    "bypass a safety device, or open the device without the right skill and equipment."
)


def credential_warning(values: dict) -> str | None:
    """Warn when text looks like a stored secret. Ordinary words such as 'charging pin' do not match."""
    blob = "\n".join(str(values.get(key, "")) for key in _TEXT_LIMITS)
    if _CREDENTIAL_PATTERN.search(blob):
        return (
            "This record looks like it includes a password, passcode, or PIN code. "
            "Do not store device credentials. Remove them if any were saved."
        )
    return None


def validate_job(data: dict) -> "RepairJobInput":
    try:
        return RepairJobInput.model_validate(data)
    except ValidationError as exc:
        parts: list[str] = []
        for error in exc.errors():
            message = str(error.get("msg", "Invalid value"))
            message = message.removeprefix("Value error, ")
            location = " ".join(str(item) for item in error.get("loc", ()))
            if location and location not in message:
                parts.append(f"{location}: {message}")
            else:
                parts.append(message)
        raise ValueError(" ".join(parts)) from exc


class RepairJobInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    customer_name: str = ""
    customer_reference: str = ""
    device_category: Literal["laptop", "phone", "tablet", "other"]
    brand: str
    model: str
    complaint: str
    visible_damage: str = ""
    accessories: str = ""
    technician_notes: str = ""

    @field_validator(
        "customer_name",
        "customer_reference",
        "brand",
        "model",
        "complaint",
        "visible_damage",
        "accessories",
        "technician_notes",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: object) -> str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ValueError("Enter text.")
        return value.strip()

    @field_validator("device_category", mode="before")
    @classmethod
    def normalize_category(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("Choose a device category.")
        return value.strip().lower()

    @model_validator(mode="after")
    def check_required(self) -> "RepairJobInput":
        if not self.customer_name and not self.customer_reference:
            raise ValueError("Enter a customer name or a customer reference.")
        missing = [
            label
            for label, value in (
                ("Brand", self.brand),
                ("Model", self.model),
                ("Customer complaint", self.complaint),
            )
            if not value
        ]
        if missing:
            raise ValueError("Required: " + ", ".join(missing) + ".")
        for field, limit in _TEXT_LIMITS.items():
            value = getattr(self, field)
            if len(value) > limit:
                raise ValueError(f"{field.replace('_', ' ').capitalize()} must be {limit} characters or fewer.")
        return self


def _as_string_list(value: object) -> object:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text[:500]] if text else []
    if isinstance(value, list):
        items: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                items.append(item.strip()[:500])
            elif isinstance(item, (int, float)) and not isinstance(item, bool):
                items.append(str(item))
        return items[:20]
    return value


def _clean_steps(steps: list[str]) -> list[str]:
    cleaned: list[str] = []
    replaced = False
    for step in steps:
        if _UNSAFE_STEP.search(step):
            if not replaced:
                cleaned.append(SAFE_STEP_REPLACEMENT)
                replaced = True
            continue
        cleaned.append(step)
    return cleaned


class PossibleExplanation(BaseModel):
    explanation: str
    confirmation: Literal["unconfirmed"] = "unconfirmed"

    @model_validator(mode="before")
    @classmethod
    def coerce_explanation(cls, value: object) -> object:
        if isinstance(value, str):
            return {"explanation": value, "confirmation": "unconfirmed"}
        if isinstance(value, dict):
            data = dict(value)
            if "explanation" not in data and isinstance(data.get("text"), str):
                data["explanation"] = data["text"]
            data["confirmation"] = "unconfirmed"
            return data
        return value

    @field_validator("explanation")
    @classmethod
    def clip_explanation(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Explanation text is empty.")
        return text[:500]


class ComplaintAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")

    complaint_summary: str
    reported_symptoms: list[str]
    missing_information: list[str]
    follow_up_questions: list[str]
    diagnostic_checklist: list[str]
    safe_inspection_steps: list[str]
    possible_explanations: list[PossibleExplanation]

    @field_validator(
        "reported_symptoms",
        "missing_information",
        "follow_up_questions",
        "diagnostic_checklist",
        "safe_inspection_steps",
        mode="before",
    )
    @classmethod
    def coerce_lists(cls, value: object) -> object:
        return _as_string_list(value)

    @field_validator("complaint_summary")
    @classmethod
    def require_summary(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("Complaint summary is empty.")
        return text[:2000]

    @field_validator("diagnostic_checklist", "safe_inspection_steps")
    @classmethod
    def remove_unsafe_steps(cls, steps: list[str]) -> list[str]:
        return _clean_steps(steps)

    @field_validator("possible_explanations")
    @classmethod
    def cap_explanations(cls, items: list[PossibleExplanation]) -> list[PossibleExplanation]:
        return items[:8]


class CustomerDraft(BaseModel):
    message: str

    @field_validator("message")
    @classmethod
    def require_message(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("The model returned an empty customer update.")
        return text
