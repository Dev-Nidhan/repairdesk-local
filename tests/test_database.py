import sqlite3

import pytest

from customer_updates import build_customer_update
from demo_data import load_demo_data
from schemas import ComplaintAnalysis, credential_warning


def test_schema_and_foreign_keys(db):
    with db.connection() as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        columns = {row[1] for row in conn.execute("PRAGMA table_info(repair_jobs)")}
    assert {
        "repair_jobs",
        "analyses",
        "estimates",
        "estimate_lines",
        "customer_updates",
        "job_counters",
    } <= tables
    assert "password" not in columns
    assert "pin" not in columns


def test_create_persists_and_ids_are_unique(db, job_fields):
    first = db.create_job(job_fields)
    second_fields = dict(job_fields)
    second_fields["customer_name"] = "O'Brien"
    second_fields["complaint"] = "Screen flicker"
    second = db.create_job(second_fields)
    assert first == "RD-0001"
    assert second == "RD-0002"
    saved = db.get_job(first)
    assert saved["customer_name"] == "Priya Raman"
    assert saved["status"] == "awaiting_inspection"
    assert saved["completed_at"] is None


def test_reference_only_and_required_fields(db, job_fields):
    reference_only = dict(job_fields)
    reference_only["customer_name"] = ""
    reference_only["customer_reference"] = "WALK-IN-4"
    job_id = db.create_job(reference_only)
    assert db.get_job(job_id)["customer_reference"] == "WALK-IN-4"

    missing_identity = dict(job_fields)
    missing_identity["customer_name"] = " "
    missing_identity["customer_reference"] = ""
    with pytest.raises(ValueError, match="customer name"):
        db.create_job(missing_identity)

    missing_complaint = dict(job_fields)
    missing_complaint["complaint"] = "  "
    with pytest.raises(ValueError, match="Customer complaint"):
        db.create_job(missing_complaint)

    with pytest.raises(ValueError, match="laptop"):
        db.create_job({**job_fields, "device_category": "watch"})


def test_extra_secret_field_is_not_stored(db, job_fields):
    job_id = db.create_job({**job_fields, "password": "hunter2"})
    saved = db.get_job(job_id)
    assert "password" not in saved
    assert saved["complaint"] == job_fields["complaint"]


def test_credential_warning_ignores_charging_pin():
    assert credential_warning({"complaint": "The charging pin is bent."}) is None
    assert credential_warning({"technician_notes": "password: 1234"}) is not None
    assert credential_warning({"complaint": "PIN code: 9988"}) is not None


def test_search_is_safe_and_matches_quotes(db, job_fields):
    db.create_job({**job_fields, "customer_name": "O'Brien", "complaint": "Screen flicker"})
    assert len(db.search("O'Brien")) == 1
    assert db.search("'; DROP TABLE repair_jobs; --") == []
    assert len(db.search()) == 1
    with db.connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM repair_jobs").fetchone()[0]
    assert count == 1


def test_update_status_and_reopen(db, job_fields):
    job_id = db.create_job(job_fields)
    db.update_job(job_id, {**job_fields, "complaint": "Fan noise after the drop."})
    updated = db.get_job(job_id)
    assert updated["complaint"] == "Fan noise after the drop."
    assert updated["status"] == "awaiting_inspection"

    db.set_status(job_id, "in_progress")
    db.set_status(job_id, "completed")
    done = db.get_job(job_id)
    assert done["status"] == "completed"
    assert done["completed_at"]
    with pytest.raises(ValueError, match="Reopen"):
        db.set_status(job_id, "in_progress")
    db.reopen_job(job_id)
    again = db.get_job(job_id)
    assert again["status"] == "in_progress"
    assert again["reopened_at"]
    assert again["completed_at"] == done["completed_at"]
    with pytest.raises(ValueError, match="completed"):
        db.reopen_job(job_id)
    with pytest.raises(KeyError):
        db.set_status("RD-9999", "in_progress")


def test_counts_follow_status(db, job_fields):
    first = db.create_job(job_fields)
    db.create_job({**job_fields, "customer_reference": "B", "customer_name": "Second"})
    db.set_status(first, "completed")
    assert db.counts() == {
        "total": 2,
        "awaiting_inspection": 1,
        "in_progress": 0,
        "completed": 1,
    }


def test_analysis_round_trip_requires_validated_model(db, job_fields):
    job_id = db.create_job(job_fields)
    with pytest.raises(TypeError):
        db.save_analysis(job_id, "gemma3:4b", {"complaint_summary": "x"})
    analysis = ComplaintAnalysis.model_validate(_analysis_payload())
    db.save_analysis(job_id, "gemma3:4b", analysis)
    saved = db.list_analyses(job_id)
    assert saved[0]["complaint_summary"] == "Shuts off under load."
    assert saved[0]["possible_explanations"][0]["confirmation"] == "unconfirmed"
    assert saved[0]["model_name"] == "gemma3:4b"


def test_customer_update_template_is_not_sent(db, job_fields):
    job_id = db.create_job(job_fields)
    job = db.get_job(job_id)
    body = build_customer_update(job, confirmed_notes="Fan spins, then the machine powers off.")
    assert job_id in body
    assert "has not been sent" in body
    assert "password" not in body.lower()
    update_id = db.save_customer_update(job_id, body, "template")
    latest = db.latest_customer_update(job_id)
    assert latest["id"] == update_id
    assert latest["source"] == "template"


def test_demo_data_is_explicit_and_has_no_fake_analysis(db):
    assert load_demo_data(db) == 3
    assert load_demo_data(db) == 0
    jobs = db.search()
    assert len(jobs) == 3
    assert db.counts() == {
        "total": 3,
        "awaiting_inspection": 1,
        "in_progress": 1,
        "completed": 1,
    }
    priced = None
    for job in jobs:
        assert job["customer_reference"].startswith("DEMO-")
        assert not job["customer_name"] or job["customer_name"].startswith("Demo Customer ")
        assert db.list_analyses(job["id"]) == []
        estimate = db.get_estimate(job["id"])
        if estimate and estimate["lines"]:
            priced = estimate
    assert priced is not None
    assert priced["status"] == "draft"
    assert priced["total_cents"] == 12400


def test_read_only_database_rejects_writes_and_preserves_fixture(db):
    from sqlite3 import OperationalError

    from database import Database

    load_demo_data(db)
    read_only_db = Database(db.path, read_only=True)
    before = read_only_db.search()

    with pytest.raises(OperationalError, match="readonly"):
        read_only_db.create_job(
            {
                "device_category": "phone",
                "customer_reference": "DEMO-9001",
                "brand": "Example",
                "model": "Sample",
                "complaint": "Fictional read-only test record.",
            }
        )

    assert read_only_db.search() == before


def test_unknown_status_rejected(db, job_fields):
    job_id = db.create_job(job_fields)
    with pytest.raises(ValueError, match="Unknown status"):
        db.set_status(job_id, "waiting_on_parts")
    with pytest.raises(sqlite3.Error):
        with db.connection() as conn:
            conn.execute("SELECT * FROM missing_table")


def _analysis_payload():
    return {
        "complaint_summary": "Shuts off under load.",
        "reported_symptoms": ["Powers on", "Shuts off under load"],
        "missing_information": ["Whether it stays on when idle"],
        "follow_up_questions": ["Does it shut off on battery and on AC?"],
        "diagnostic_checklist": ["Confirm the charger output with a known-good cable"],
        "safe_inspection_steps": ["Look for swelling, heat, or a loose charger"],
        "possible_explanations": [
            {"explanation": "A weak battery is possible.", "confirmation": "unconfirmed"}
        ],
    }
