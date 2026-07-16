"""Pure CSV parsing helpers shared by local and asynchronous processors."""

import csv
import io


def parse_financial_csv(csv_text: str) -> list[dict[str, str | float]]:
    """Parse financial CSV text into normalized record dictionaries."""
    reader = csv.DictReader(io.StringIO(csv_text))
    records: list[dict[str, str | float]] = []

    for row_number, row in enumerate(reader, start=2):
        raw_amount = row.get("amount", "") or "0"
        try:
            amount = float(raw_amount)
        except ValueError as exc:
            raise ValueError(f"Invalid amount on row {row_number}") from exc

        records.append(
            {
                "date": row.get("date", ""),
                "description": row.get("description", ""),
                "amount": amount,
                "category": row.get("category", "") or "Uncategorised",
            }
        )

    return records
