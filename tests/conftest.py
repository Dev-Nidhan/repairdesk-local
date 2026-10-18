import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import Database


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "repairdesk.db")


@pytest.fixture
def job_fields():
    return {
        "customer_name": "Priya Raman",
        "customer_reference": "",
        "device_category": "laptop",
        "brand": "Dell",
        "model": "Latitude 5420",
        "complaint": "The laptop powers on, then shuts off under load.",
        "visible_damage": "Worn palm rest.",
        "accessories": "Charger.",
        "technician_notes": "No liquid damage seen.",
    }
