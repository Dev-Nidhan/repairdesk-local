"""Manual estimate math. Prices are never invented here."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from schemas import LINE_TYPES

_MAX_QUANTITY = Decimal("10000")
_MAX_PRICE = Decimal("1000000")


def _to_decimal(value: object, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"Enter a valid {label}.")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            raise ValueError(f"Enter a valid {label}.")
        try:
            return Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(f"Enter a valid {label}.") from exc
    raise ValueError(f"Enter a valid {label}.")


def parse_quantity(value: object) -> int:
    """Return quantity in hundredths. 1.50 hours becomes 150."""
    quantity = _to_decimal(value, "quantity")
    if quantity < 0:
        raise ValueError("Quantity cannot be negative.")
    if quantity > _MAX_QUANTITY:
        raise ValueError("Quantity is too large.")
    hundredths = (quantity * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(hundredths)


def parse_money(value: object) -> int:
    """Return a manually entered price in integer cents."""
    amount = _to_decimal(value, "price")
    if amount < 0:
        raise ValueError("Price cannot be negative.")
    if amount > _MAX_PRICE:
        raise ValueError("Price is too large.")
    cents = (amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def line_total_cents(quantity_hundredths: int, unit_price_cents: int) -> int:
    if quantity_hundredths < 0 or unit_price_cents < 0:
        raise ValueError("Quantity and price cannot be negative.")
    product = (Decimal(quantity_hundredths) * Decimal(unit_price_cents)) / Decimal(100)
    return int(product.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_line(line_type: str, description: object, quantity: object, unit_price: object) -> dict:
    if line_type not in LINE_TYPES:
        raise ValueError("Line type must be part or labour.")
    if not isinstance(description, str):
        raise ValueError("Enter a description for the line.")
    text = description.strip()
    if not text:
        raise ValueError("Enter a description for the line.")
    if len(text) > 300:
        raise ValueError("Description must be 300 characters or fewer.")
    quantity_hundredths = parse_quantity(quantity)
    unit_price_cents = parse_money(unit_price)
    return {
        "line_type": line_type,
        "description": text,
        "quantity_hundredths": quantity_hundredths,
        "unit_price_cents": unit_price_cents,
        "line_total_cents": line_total_cents(quantity_hundredths, unit_price_cents),
    }


def summarize_lines(lines: list[dict]) -> dict:
    parts = 0
    labour = 0
    for line in lines:
        total = line.get("line_total_cents")
        if total is None:
            total = line_total_cents(int(line["quantity_hundredths"]), int(line["unit_price_cents"]))
        if line["line_type"] == "part":
            parts += int(total)
        elif line["line_type"] == "labour":
            labour += int(total)
        else:
            raise ValueError("Unknown line type.")
    return {
        "parts_cents": parts,
        "labour_cents": labour,
        "total_cents": parts + labour,
    }


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, fraction = divmod(abs(int(cents)), 100)
    return f"{sign}{whole}.{fraction:02d}"


def format_quantity(quantity_hundredths: int) -> str:
    whole, fraction = divmod(abs(int(quantity_hundredths)), 100)
    sign = "-" if quantity_hundredths < 0 else ""
    return f"{sign}{whole}.{fraction:02d}"


def display_currency(explicit: str | None, database_exists: bool) -> str:
    """Choose a money label without converting stored amounts.

    An explicit setting always wins. A database that already exists keeps the
    historical USD label. A new database with no setting uses INR.
    """
    if explicit is not None and explicit.strip():
        return explicit.strip()
    return "USD" if database_exists else "INR"
