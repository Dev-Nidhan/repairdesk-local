"""SQLite storage for repair jobs. Connections are opened per operation."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from estimates import line_total_cents, parse_line, summarize_lines
from schemas import ESTIMATE_STATUSES, JOB_STATUSES, ComplaintAnalysis, validate_job

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS job_counters (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        next_number INTEGER NOT NULL
    )
    """,
    "INSERT OR IGNORE INTO job_counters (id, next_number) VALUES (1, 1)",
    """
    CREATE TABLE IF NOT EXISTS repair_jobs (
        id TEXT PRIMARY KEY,
        customer_name TEXT NOT NULL DEFAULT '',
        customer_reference TEXT NOT NULL DEFAULT '',
        device_category TEXT NOT NULL CHECK (device_category IN ('laptop', 'phone', 'tablet', 'other')),
        brand TEXT NOT NULL,
        model TEXT NOT NULL,
        complaint TEXT NOT NULL,
        visible_damage TEXT NOT NULL DEFAULT '',
        accessories TEXT NOT NULL DEFAULT '',
        technician_notes TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL CHECK (status IN ('awaiting_inspection', 'in_progress', 'completed'))
            DEFAULT 'awaiting_inspection',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT,
        reopened_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT NOT NULL REFERENCES repair_jobs(id) ON DELETE CASCADE,
        model_name TEXT NOT NULL,
        complaint_summary TEXT NOT NULL,
        reported_symptoms_json TEXT NOT NULL,
        missing_information_json TEXT NOT NULL,
        follow_up_questions_json TEXT NOT NULL,
        diagnostic_checklist_json TEXT NOT NULL,
        safe_inspection_steps_json TEXT NOT NULL,
        possible_explanations_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS estimates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT NOT NULL UNIQUE REFERENCES repair_jobs(id) ON DELETE CASCADE,
        status TEXT NOT NULL CHECK (status IN ('draft', 'approved', 'declined')) DEFAULT 'draft',
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS estimate_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        estimate_id INTEGER NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,
        line_type TEXT NOT NULL CHECK (line_type IN ('part', 'labour')),
        description TEXT NOT NULL,
        quantity_hundredths INTEGER NOT NULL CHECK (quantity_hundredths >= 0),
        unit_price_cents INTEGER NOT NULL CHECK (unit_price_cents >= 0)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS customer_updates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT NOT NULL REFERENCES repair_jobs(id) ON DELETE CASCADE,
        body TEXT NOT NULL,
        source TEXT NOT NULL CHECK (source IN ('template', 'ollama')),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
)

_ANALYSIS_JSON_FIELDS = (
    "reported_symptoms",
    "missing_information",
    "follow_up_questions",
    "diagnostic_checklist",
    "safe_inspection_steps",
    "possible_explanations",
)

_SEARCH_COLUMNS = (
    "id",
    "customer_name",
    "customer_reference",
    "brand",
    "model",
    "complaint",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: str | Path, *, read_only: bool = False) -> None:
        self.path = Path(path)
        self.read_only = read_only
        if read_only:
            if not self.path.is_file():
                raise FileNotFoundError(f"Read-only database does not exist: {self.path}")
        else:
            self.init()

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as conn:
            for statement in _SCHEMA:
                conn.execute(statement)

    @contextmanager
    def connection(self):
        if self.read_only:
            uri = f"{self.path.resolve().as_uri()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
        else:
            conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        if not self.read_only:
            conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_job(self, data: dict) -> str:
        job = validate_job(data)
        now = utc_now()
        with self.connection() as conn:
            job_id = self._next_job_id(conn)
            conn.execute(
                """
                INSERT INTO repair_jobs (
                    id, customer_name, customer_reference, device_category, brand, model,
                    complaint, visible_damage, accessories, technician_notes, status,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'awaiting_inspection', ?, ?)
                """,
                (
                    job_id,
                    job.customer_name,
                    job.customer_reference,
                    job.device_category,
                    job.brand,
                    job.model,
                    job.complaint,
                    job.visible_damage,
                    job.accessories,
                    job.technician_notes,
                    now,
                    now,
                ),
            )
        return job_id

    def update_job(self, job_id: str, data: dict) -> None:
        job = validate_job(data)
        if self.get_job(job_id) is None:
            raise KeyError(job_id)
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE repair_jobs SET
                    customer_name = ?,
                    customer_reference = ?,
                    device_category = ?,
                    brand = ?,
                    model = ?,
                    complaint = ?,
                    visible_damage = ?,
                    accessories = ?,
                    technician_notes = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    job.customer_name,
                    job.customer_reference,
                    job.device_category,
                    job.brand,
                    job.model,
                    job.complaint,
                    job.visible_damage,
                    job.accessories,
                    job.technician_notes,
                    utc_now(),
                    job_id,
                ),
            )

    def get_job(self, job_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM repair_jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def search(self, query: str = "", status: str | None = None) -> list[dict]:
        clauses: list[str] = []
        params: list[str] = []
        text = query.strip()
        if text:
            like = f"%{text}%"
            clauses.append("(" + " OR ".join(f"{column} LIKE ?" for column in _SEARCH_COLUMNS) + ")")
            params.extend([like] * len(_SEARCH_COLUMNS))
        if status:
            if status not in JOB_STATUSES:
                raise ValueError("Unknown status.")
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM repair_jobs {where} ORDER BY updated_at DESC, id DESC"
        with self.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def counts(self) -> dict:
        totals = {"total": 0, "awaiting_inspection": 0, "in_progress": 0, "completed": 0}
        with self.connection() as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS n FROM repair_jobs GROUP BY status").fetchall()
        for row in rows:
            totals[row["status"]] = row["n"]
            totals["total"] += row["n"]
        return totals

    def recent(self, limit: int = 8) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM repair_jobs ORDER BY updated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def set_status(self, job_id: str, status: str) -> None:
        if status not in JOB_STATUSES:
            raise ValueError("Unknown status.")
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job["status"] == "completed" and status != "completed":
            raise ValueError("Reopen the job before changing its status.")
        now = utc_now()
        completed_at = job["completed_at"]
        if status == "completed":
            completed_at = now
        with self.connection() as conn:
            conn.execute(
                "UPDATE repair_jobs SET status = ?, updated_at = ?, completed_at = ? WHERE id = ?",
                (status, now, completed_at, job_id),
            )

    def reopen_job(self, job_id: str, status: str = "in_progress") -> None:
        if status not in JOB_STATUSES or status == "completed":
            raise ValueError("Choose a working status to reopen the job.")
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job["status"] != "completed":
            raise ValueError("Only a completed job can be reopened.")
        now = utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE repair_jobs
                SET status = ?, updated_at = ?, reopened_at = ?
                WHERE id = ?
                """,
                (status, now, now, job_id),
            )

    def save_analysis(self, job_id: str, model_name: str, analysis: ComplaintAnalysis) -> int:
        if not isinstance(analysis, ComplaintAnalysis):
            # Streamlit can reload the script module and produce a second copy of the
            # same Pydantic class. Re-validate that copy here; plain dicts stay rejected.
            dump = getattr(analysis, "model_dump", None)
            if dump is None:
                raise TypeError("Only a validated analysis can be saved.")
            analysis = ComplaintAnalysis.model_validate(dump())
        if self.get_job(job_id) is None:
            raise KeyError(job_id)
        payload = analysis.model_dump()
        now = utc_now()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO analyses (
                    job_id, model_name, complaint_summary,
                    reported_symptoms_json, missing_information_json, follow_up_questions_json,
                    diagnostic_checklist_json, safe_inspection_steps_json, possible_explanations_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    model_name,
                    payload["complaint_summary"],
                    *(json.dumps(payload[field]) for field in _ANALYSIS_JSON_FIELDS),
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def list_analyses(self, job_id: str) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM analyses WHERE job_id = ? ORDER BY id DESC",
                (job_id,),
            ).fetchall()
        return [_analysis_from_row(row) for row in rows]

    def ensure_estimate(self, job_id: str) -> dict:
        if self.get_job(job_id) is None:
            raise KeyError(job_id)
        existing = self.get_estimate(job_id)
        if existing:
            return existing
        now = utc_now()
        try:
            with self.connection() as conn:
                conn.execute(
                    """
                    INSERT INTO estimates (job_id, status, notes, created_at, updated_at)
                    VALUES (?, 'draft', '', ?, ?)
                    """,
                    (job_id, now, now),
                )
        except sqlite3.IntegrityError:
            pass
        estimate = self.get_estimate(job_id)
        if estimate is None:
            raise KeyError(job_id)
        return estimate

    def get_estimate(self, job_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM estimates WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            lines = conn.execute(
                """
                SELECT * FROM estimate_lines
                WHERE estimate_id = ?
                ORDER BY id
                """,
                (row["id"],),
            ).fetchall()
        parsed_lines = []
        for line in lines:
            item = dict(line)
            item["line_total_cents"] = line_total_cents(
                int(item["quantity_hundredths"]),
                int(item["unit_price_cents"]),
            )
            parsed_lines.append(item)
        estimate = dict(row)
        estimate["lines"] = parsed_lines
        estimate.update(summarize_lines(parsed_lines))
        return estimate

    def add_estimate_line(
        self,
        job_id: str,
        line_type: str,
        description: str,
        quantity: object,
        unit_price: object,
    ) -> dict:
        parsed = parse_line(line_type, description, quantity, unit_price)
        estimate = self.ensure_estimate(job_id)
        now = utc_now()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO estimate_lines (
                    estimate_id, line_type, description, quantity_hundredths, unit_price_cents
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    estimate["id"],
                    parsed["line_type"],
                    parsed["description"],
                    parsed["quantity_hundredths"],
                    parsed["unit_price_cents"],
                ),
            )
            conn.execute(
                "UPDATE estimates SET status = 'draft', updated_at = ? WHERE id = ?",
                (now, estimate["id"]),
            )
        saved = self.get_estimate(job_id)
        if saved is None:
            raise KeyError(job_id)
        return saved

    def remove_estimate_line(self, job_id: str, line_id: int) -> None:
        estimate = self.get_estimate(job_id)
        if estimate is None:
            raise KeyError(job_id)
        if not any(line["id"] == line_id for line in estimate["lines"]):
            raise KeyError(line_id)
        with self.connection() as conn:
            conn.execute(
                "DELETE FROM estimate_lines WHERE id = ? AND estimate_id = ?",
                (line_id, estimate["id"]),
            )
            conn.execute(
                "UPDATE estimates SET status = 'draft', updated_at = ? WHERE id = ?",
                (utc_now(), estimate["id"]),
            )

    def set_estimate_status(self, job_id: str, status: str) -> None:
        if status not in ESTIMATE_STATUSES:
            raise ValueError("Estimate status must be draft, approved, or declined.")
        estimate = self.get_estimate(job_id)
        if estimate is None:
            raise KeyError("No estimate for this job.")
        if status == "approved" and not estimate["lines"]:
            raise ValueError("Add at least one line before approving an estimate.")
        with self.connection() as conn:
            conn.execute(
                "UPDATE estimates SET status = ?, updated_at = ? WHERE id = ?",
                (status, utc_now(), estimate["id"]),
            )

    def set_estimate_notes(self, job_id: str, notes: str) -> None:
        estimate = self.get_estimate(job_id)
        if estimate is None:
            raise KeyError("No estimate for this job.")
        text = notes.strip()
        if len(text) > 2000:
            raise ValueError("Estimate notes must be 2000 characters or fewer.")
        with self.connection() as conn:
            conn.execute(
                "UPDATE estimates SET notes = ?, updated_at = ? WHERE id = ?",
                (text, utc_now(), estimate["id"]),
            )

    def save_customer_update(self, job_id: str, body: str, source: str) -> int:
        if source not in ("template", "ollama"):
            raise ValueError("Unknown update source.")
        text = body.strip()
        if not text:
            raise ValueError("The update is empty.")
        if self.get_job(job_id) is None:
            raise KeyError(job_id)
        now = utc_now()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO customer_updates (job_id, body, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, text, source, now, now),
            )
            return int(cursor.lastrowid)

    def latest_customer_update(self, job_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM customer_updates
                WHERE job_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (job_id,),
            ).fetchone()
        return dict(row) if row else None

    def _next_job_id(self, conn: sqlite3.Connection) -> str:
        row = conn.execute("SELECT next_number FROM job_counters WHERE id = 1").fetchone()
        number = int(row["next_number"])
        conn.execute("UPDATE job_counters SET next_number = ? WHERE id = 1", (number + 1,))
        return f"RD-{number:04d}"


def _analysis_from_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    for field in _ANALYSIS_JSON_FIELDS:
        data[field] = json.loads(data.pop(f"{field}_json"))
    return data
