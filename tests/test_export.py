from __future__ import annotations

import csv
import json

import pytest

from booking_scraper.export import CSV_FIELDS, format_for, to_csv, to_jsonl, write
from booking_scraper.models import Property


@pytest.fixture
def props():
    return [
        Property(
            property_id=1,
            name="H\u00f4tel Un",
            price=120.5,
            currency="EUR",
            deals=["Limited-time Deal"],
            highlights=["Free Wifi", "Garden"],
            free_cancellation=True,
        ),
        Property(property_id=2, name="Hotel Two"),
    ]


def test_csv_flattens_lists_and_booleans(props):
    rows = list(csv.DictReader(to_csv(props).splitlines()))
    assert list(rows[0].keys()) == CSV_FIELDS
    assert rows[0]["highlights"] == "Free Wifi; Garden"
    assert rows[0]["free_cancellation"] == "true"
    assert rows[1]["price"] == "" and rows[1]["sponsored"] == "false"


def test_jsonl(props):
    lines = to_jsonl(props).splitlines()
    assert [json.loads(line)["property_id"] for line in lines] == [1, 2]


@pytest.mark.parametrize(
    "path, explicit, expected",
    [
        ("out.csv", None, "csv"),
        ("out.JSONL", None, "jsonl"),
        ("out.txt", None, "json"),
        (None, None, "json"),
        ("out.csv", "json", "json"),
    ],
)
def test_format_for(path, explicit, expected):
    assert format_for(path, explicit) == expected


def test_format_for_rejects_unknown():
    with pytest.raises(ValueError):
        format_for("x.json", "xml")


def test_write_files(props, tmp_path):
    json_path = write(props, tmp_path / "hotels.json")
    assert json.loads(json_path.read_text(encoding="utf-8"))[0]["name"] == "H\u00f4tel Un"
    csv_path = write(props, tmp_path / "hotels.csv")
    assert csv_path.read_bytes().startswith(b"\xef\xbb\xbf")  # BOM for Excel
