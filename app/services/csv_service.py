"""Pure CSV parsing helpers shared by local and asynchronous processors."""

import csv
import io
import math

REQUIRED_HEADERS = {"date", "description", "amount", "category"}


def financial_csv_reader(csv_text: str) -> csv.DictReader:
    """Return a reader whose headers match the validated canonical schema."""
    reader = csv.DictReader(io.StringIO(csv_text))
    normalized_headers = [
        header.strip() if header is not None else ""
        for header in (reader.fieldnames or [])
    ]
    if not normalized_headers or any(not header for header in normalized_headers):
        raise ValueError("CSV headers must be non-empty")
    if len(normalized_headers) != len(set(normalized_headers)):
        raise ValueError("CSV headers must be unique after whitespace normalization")
    reader.fieldnames = normalized_headers
    return reader


def parse_financial_csv(csv_text: str) -> list[dict[str, str | float]]:
    """Parse financial CSV text into normalized record dictionaries."""
    reader = financial_csv_reader(csv_text)
    records: list[dict[str, str | float]] = []

    for row_number, row in enumerate(reader, start=2):
        raw_amount = row.get("amount", "") or "0"
        try:
            amount = float(raw_amount)
        except ValueError as exc:
            raise ValueError(f"Invalid amount on row {row_number}") from exc
        if not math.isfinite(amount):
            raise ValueError(f"Amount must be finite on row {row_number}")

        records.append(
            {
                "date": row.get("date", ""),
                "description": row.get("description", ""),
                "amount": amount,
                "category": row.get("category", "") or "Uncategorised",
            }
        )

    return records
