"""Write scraped properties to JSON, JSON Lines or CSV."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Sequence
from dataclasses import fields
from pathlib import Path
from typing import Any

from .models import Property

CSV_FIELDS: list[str] = [f.name for f in fields(Property)]
FORMATS = ("json", "jsonl", "csv")


def _as_dict(item: Any) -> dict[str, Any]:
    return item.to_dict() if hasattr(item, "to_dict") else dict(item)


def _csv_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else value


def to_json(items: Iterable[Any], *, indent: int | None = 2) -> str:
    return json.dumps([_as_dict(i) for i in items], indent=indent, ensure_ascii=False)


def to_jsonl(items: Iterable[Any]) -> str:
    return "".join(json.dumps(_as_dict(i), ensure_ascii=False) + "\n" for i in items)


def to_csv(items: Iterable[Any], columns: Sequence[str] | None = None) -> str:
    """CSV text; list fields (deals, highlights) are joined with ``"; "``."""
    rows = [_as_dict(i) for i in items]
    columns = list(columns or (CSV_FIELDS if not rows or "property_id" in rows[0] else rows[0]))
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: _csv_value(row.get(k)) for k in columns})
    return buf.getvalue()


def format_for(path: str | Path | None, explicit: str | None = None) -> str:
    """Pick an output format from an explicit choice or the file extension."""
    if explicit:
        if explicit not in FORMATS:
            raise ValueError(f"format must be one of {FORMATS}")
        return explicit
    suffix = Path(path).suffix.lower().lstrip(".") if path else ""
    return suffix if suffix in FORMATS else "json"


def render(items: Iterable[Any], fmt: str) -> str:
    if fmt == "csv":
        return to_csv(items)
    if fmt == "jsonl":
        return to_jsonl(items)
    return to_json(items) + "\n"


def write(items: Iterable[Any], path: str | Path, fmt: str | None = None) -> Path:
    """Write ``items`` to ``path`` (format from ``fmt`` or the extension)."""
    path = Path(path)
    text = render(list(items), format_for(path, fmt))
    # utf-8-sig so Excel opens CSVs with accented hotel names correctly.
    encoding = "utf-8-sig" if format_for(path, fmt) == "csv" else "utf-8"
    path.write_text(text, encoding=encoding, newline="")
    return path
