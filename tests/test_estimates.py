import pytest

from estimates import (
    display_currency,
    format_cents,
    line_total_cents,
    parse_line,
    parse_money,
    parse_quantity,
)


def test_parts_and_labour_total_matches_the_shop_example():
    battery = parse_line("part", "Battery", "2", "12.50")
    labour = parse_line("labour", "Diagnosis", "1.5", "40.00")
    assert battery["line_total_cents"] == 2500
    assert labour["line_total_cents"] == 6000
    assert battery["line_total_cents"] + labour["line_total_cents"] == 8500
    assert format_cents(8500) == "85.00"


def test_decimal_quantity_rounds_half_up_and_zero_is_allowed():
    assert line_total_cents(parse_quantity("1.25"), parse_money("10.10")) == 1263
    assert parse_quantity("0") == 0
    assert line_total_cents(0, 1250) == 0
    assert parse_line("part", "Screw", 0, "1.00")["line_total_cents"] == 0


def test_negative_and_blank_values_are_rejected():
    with pytest.raises(ValueError, match="negative"):
        parse_money("-1")
    with pytest.raises(ValueError, match="negative"):
        parse_quantity("-0.25")
    with pytest.raises(ValueError, match="description"):
        parse_line("part", "  ", "1", "5")
    with pytest.raises(ValueError, match="part or labour"):
        parse_line("fee", "Bench fee", "1", "5")


def test_estimate_stays_draft_until_technician_approves(db, job_fields):
    job_id = db.create_job(job_fields)
    estimate = db.ensure_estimate(job_id)
    assert estimate["status"] == "draft"
    with pytest.raises(ValueError, match="at least one line"):
        db.set_estimate_status(job_id, "approved")

    db.add_estimate_line(job_id, "part", "Battery", "2", "12.50")
    db.add_estimate_line(job_id, "labour", "Diagnosis", "1.5", "40.00")
    priced = db.get_estimate(job_id)
    assert priced["status"] == "draft"
    assert priced["parts_cents"] == 2500
    assert priced["labour_cents"] == 6000
    assert priced["total_cents"] == 8500
    assert priced["lines"][0]["unit_price_cents"] == 1250

    db.set_estimate_status(job_id, "approved")
    assert db.get_estimate(job_id)["status"] == "approved"
    db.add_estimate_line(job_id, "part", "Adhesive", "1", "5.00")
    revised = db.get_estimate(job_id)
    assert revised["status"] == "draft"
    assert revised["total_cents"] == 9000

    db.set_estimate_status(job_id, "declined")
    assert db.get_estimate(job_id)["status"] == "declined"
    line_id = revised["lines"][0]["id"]
    db.remove_estimate_line(job_id, line_id)
    assert db.get_estimate(job_id)["status"] == "draft"


def test_notes_do_not_approve_or_invent_a_price(db, job_fields):
    job_id = db.create_job(job_fields)
    db.ensure_estimate(job_id)
    db.set_estimate_notes(job_id, "Customer will decide tomorrow.")
    estimate = db.get_estimate(job_id)
    assert estimate["status"] == "draft"
    assert estimate["notes"] == "Customer will decide tomorrow."
    assert estimate["total_cents"] == 0
    assert estimate["lines"] == []


def test_currency_label_does_not_relabel_an_existing_database():
    assert display_currency("INR", True) == "INR"
    assert display_currency("  USD  ", False) == "USD"
    assert display_currency(None, True) == "USD"
    assert display_currency("   ", True) == "USD"
    assert display_currency(None, False) == "INR"
    assert display_currency("", False) == "INR"
