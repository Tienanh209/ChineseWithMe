"""Reading import files: CSV (one row per word) and JSON (full detail)."""

import csv
import io
import json
import re
from dataclasses import dataclass
from typing import Any

_LANG_COLUMN = re.compile(r"[a-z]{2}")
_EXAMPLE_LANG_COLUMN = re.compile(r"example_([a-z]{2})")
_SINGLE_COLUMNS = {
    "traditional",
    "simplified",
    "pinyin",
    "zhuyin",
    "part_of_speech",
    "level",
    "audio_path",
    "groups",
    "example_hanzi",
    "example_pinyin",
    "example_zhuyin",
    "example_audio_path",
}
_REQUIRED_COLUMNS = ("traditional", "pinyin", "level")
_EXTRA = "__extra__"
TOO_MANY_CELLS = "__too_many_cells__"


class ImportFileError(ValueError):
    """The file as a whole cannot be read. Nothing is imported."""


@dataclass(frozen=True)
class RawRow:
    number: int  # CSV: line in the file (header is 1). JSON: position in the list (first is 1).
    data: Any


def detect_format(text: str, filename: str | None = None) -> str:
    if filename:
        lower = filename.lower()
        if lower.endswith(".json"):
            return "json"
        if lower.endswith((".csv", ".tsv", ".txt")):
            return "csv"
    return "json" if text.lstrip()[:1] in ("[", "{") else "csv"


def parse(
    text: str, fmt: str | None = None, *, filename: str | None = None, max_rows: int | None = None
) -> list[RawRow]:
    text = text.lstrip("﻿")  # BOM from Excel
    if not text.strip():
        raise ImportFileError("the file is empty")
    fmt = fmt or detect_format(text, filename)
    if fmt not in ("csv", "json"):
        raise ImportFileError(f"unknown format {fmt!r}: use csv or json")
    rows = _parse_json(text) if fmt == "json" else _parse_csv(text)
    if max_rows is not None and len(rows) > max_rows:
        raise ImportFileError(f"too many rows: {len(rows)} (the limit here is {max_rows})")
    return rows


def _parse_json(text: str) -> list[RawRow]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ImportFileError(f"invalid JSON: {exc.msg} (line {exc.lineno}, column {exc.colno})") from exc
    if isinstance(data, dict):
        data = data.get("words")
    if not isinstance(data, list):
        raise ImportFileError('JSON must be a list of words, or an object like {"words": [...]}')
    return [RawRow(i, item) for i, item in enumerate(data, start=1)]


def _split(cell: str | None) -> list[str]:
    return [part.strip() for part in (cell or "").split(";") if part.strip()]


def _parse_csv(text: str) -> list[RawRow]:
    header_line = text.splitlines()[0]
    # Excel in Vietnamese and many European locales writes ';' between columns.
    delimiter = max((",", ";", "\t"), key=header_line.count)
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter, restkey=_EXTRA)
    names = [(name or "").strip().lower() for name in (reader.fieldnames or [])]
    if len(set(names)) != len(names):
        raise ImportFileError("duplicate column names in the header")
    reader.fieldnames = names

    lang_cols = [n for n in names if _LANG_COLUMN.fullmatch(n)]
    example_lang_cols = [n for n in names if _EXAMPLE_LANG_COLUMN.fullmatch(n)]
    unknown = [n for n in names if n not in _SINGLE_COLUMNS and n not in lang_cols and n not in example_lang_cols]
    if unknown:
        raise ImportFileError(
            f"unknown column(s): {', '.join(unknown)}. Known: traditional, simplified, pinyin, zhuyin, "
            "part_of_speech, level, audio_path, groups, one two-letter column per language (vi, en), "
            "example_hanzi, example_pinyin, example_zhuyin, example_audio_path, example_<lang>"
        )
    missing = [c for c in _REQUIRED_COLUMNS if c not in names]
    if missing or not lang_cols:
        need = missing + ([] if lang_cols else ["a meaning column such as vi or en"])
        raise ImportFileError(f"missing column(s): {', '.join(need)}")

    rows: list[RawRow] = []
    for record in reader:
        if not any((v or "").strip() for k, v in record.items() if k != _EXTRA and isinstance(v, str)):
            continue  # blank line
        if _EXTRA in record:
            rows.append(RawRow(reader.line_num, TOO_MANY_CELLS))
            continue
        rows.append(RawRow(reader.line_num, _csv_record_to_word(record, lang_cols, example_lang_cols)))
    return rows


def _csv_record_to_word(record: dict[str, str | None], lang_cols: list[str], example_lang_cols: list[str]) -> dict:
    cell = lambda name: (record.get(name) or "").strip()  # noqa: E731
    word: dict[str, Any] = {
        "traditional": cell("traditional"),
        "pinyin": cell("pinyin"),
        "level": cell("level"),
        "translations": {lang: _split(record.get(lang)) for lang in lang_cols},
        "groups": _split(record.get("groups")),
    }
    for optional in ("simplified", "zhuyin", "part_of_speech", "audio_path"):
        if cell(optional):
            word[optional] = cell(optional)
    example_cells = {
        "hanzi": cell("example_hanzi"),
        "pinyin": cell("example_pinyin"),
        "zhuyin": cell("example_zhuyin"),
        "audio_path": cell("example_audio_path"),
    }
    example_translations = {c.removeprefix("example_"): cell(c) for c in example_lang_cols if cell(c)}
    if any(example_cells.values()) or example_translations:
        word["examples"] = [{**example_cells, "translations": example_translations}]
    return word
