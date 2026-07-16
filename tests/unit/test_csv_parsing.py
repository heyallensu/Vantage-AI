from pathlib import Path

import pytest

from app.services.csv_service import parse_financial_csv

SAMPLE_DATA = Path(__file__).parents[2] / "sample-data.csv"


def test_parse_financial_csv_returns_all_sample_rows() -> None:
    records = parse_financial_csv(SAMPLE_DATA.read_text(encoding="utf-8"))

    assert len(records) == 10
    assert records[0] == {
        "date": "2024-01-05",
        "description": "AWS Cloud Services",
        "amount": 1250.0,
        "category": "Technology",
    }
    assert max(record["amount"] for record in records) == 75000.0


def test_parse_financial_csv_rejects_invalid_amount() -> None:
    csv_text = "date,description,amount,category\n2024-01-01,Bad row,not-a-number,Unknown\n"

    with pytest.raises(ValueError, match="Invalid amount on row 2"):
        parse_financial_csv(csv_text)
