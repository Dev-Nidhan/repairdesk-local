"""Fictional shop records. Loaded only when a person asks for sample data."""

from __future__ import annotations

from database import Database

_SAMPLES = (
    {
        "customer_name": "Demo Customer One",
        "customer_reference": "DEMO-1001",
        "device_category": "phone",
        "brand": "Northwind",
        "model": "A8",
        "complaint": "The phone shuts off when the battery indicator still shows about 30 percent.",
        "visible_damage": "Hairline crack on the back glass.",
        "accessories": "USB-C cable. No adapter.",
        "technician_notes": "Sample record. Customer wants an estimate before any parts are ordered.",
        "status": "awaiting_inspection",
    },
    {
        "customer_name": "Demo Customer Two",
        "customer_reference": "DEMO-1002",
        "device_category": "laptop",
        "brand": "Harbor",
        "model": "13",
        "complaint": "The laptop does not detect the internal drive after it was dropped.",
        "visible_damage": "Dented left front corner.",
        "accessories": "Charger and sleeve.",
        "technician_notes": "Sample record. External visual inspection only so far.",
        "status": "in_progress",
        "estimate": (
            {
                "line_type": "labour",
                "description": "Diagnosis and internal inspection",
                "quantity": "1.00",
                "unit_price": "45.00",
            },
            {
                "line_type": "part",
                "description": "Replacement drive, price entered by the technician",
                "quantity": "1",
                "unit_price": "79.00",
            },
        ),
    },
    {
        "customer_name": "",
        "customer_reference": "DEMO-1003",
        "device_category": "tablet",
        "brand": "Field",
        "model": "Note",
        "complaint": "Touch stops responding along the left edge.",
        "visible_damage": "No cracks.",
        "accessories": "None received.",
        "technician_notes": "Sample record. Marked complete after a calibration check.",
        "status": "completed",
    },
)


def load_demo_data(db: Database) -> int:
    existing = {job["customer_reference"] for job in db.search()}
    added = 0
    for sample in _SAMPLES:
        if sample["customer_reference"] in existing:
            continue
        payload = {key: sample[key] for key in sample if key not in {"status", "estimate"}}
        job_id = db.create_job(payload)
        status = sample["status"]
        if status != "awaiting_inspection":
            db.set_status(job_id, status)
        for line in sample.get("estimate", ()):
            db.add_estimate_line(
                job_id,
                line["line_type"],
                line["description"],
                line["quantity"],
                line["unit_price"],
            )
        added += 1
    return added
