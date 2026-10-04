"""Validate the model's comedic analysis and manage tag status."""

from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple, TextIO

from jsonschema import Draft202012Validator

from .library import (
    SKILL_DIR,
    TAG_FIELDS,
    LibraryError,
    get_entry,
    index_lock,
    load_index,
    remove_frames,
    save_index,
)

VOCAB_FIELDS = ("humor_mechanisms", "emotions")


def load_vocabulary() -> dict[str, list[str]]:
    return json.loads((SKILL_DIR / "vocabulary.json").read_text(encoding="utf-8"))


def load_schema() -> dict:
    return json.loads((SKILL_DIR / "schema.json").read_text(encoding="utf-8"))


def validate_payload(payload: object) -> list[str]:
    errors = []
    validator = Draft202012Validator(load_schema())
    for error in sorted(validator.iter_errors(payload), key=lambda e: [str(p) for p in e.path]):
        where = "/".join(str(p) for p in error.path) or "(payload)"
        errors.append(f"{where}: {error.message}")
    if not isinstance(payload, dict):
        return errors
    vocab = load_vocabulary()
    for field in VOCAB_FIELDS:
        values = payload.get(field)
        if not isinstance(values, list):
            continue
        unknown = [v for v in values if isinstance(v, str) and v not in vocab[field]]
        if unknown:
            errors.append(f"{field}: unknown term(s) {unknown}. Allowed: {', '.join(vocab[field])}")
    return errors


def _decode(data: bytes) -> str:
    """UTF-8 (with or without BOM), or UTF-16 with a BOM as Windows PowerShell 5.1 writes."""
    encoding = "utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
    try:
        return data.decode(encoding)
    except UnicodeDecodeError as e:
        raise LibraryError(f"Payload file is not UTF-8 text ({e}). Save it as UTF-8.") from e


def _read_text(source: str, stdin: TextIO | None = None) -> str:
    try:
        if source == "-":
            raw = (stdin or sys.stdin).read()
        else:
            raw = _decode(Path(source).read_bytes())
    except OSError as e:
        raise LibraryError(f"Cannot read payload: {e}") from e
    return raw.lstrip("\ufeff")


def read_payload(source: str, stdin: TextIO | None = None) -> object:
    raw = _read_text(source, stdin)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise LibraryError(f"Payload is not valid JSON: {e}") from e


class BadLine(NamedTuple):
    """A JSON Lines row that didn't parse; tag_batch rejects it with this error."""

    error: str


def read_jsonl(source: str, stdin: TextIO | None = None) -> list[tuple[int, object]]:
    """(line number, parsed object or BadLine) for each non-blank line."""
    rows: list[tuple[int, object]] = []
    for number, line in enumerate(_read_text(source, stdin).splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append((number, json.loads(line)))
        except json.JSONDecodeError as e:
            rows.append((number, BadLine(f"not valid JSON: {e}")))
    return rows


def _clear_tags(entry: dict) -> None:
    for field in TAG_FIELDS:
        entry.pop(field, None)
    entry["status"] = "untagged"


def _apply_tag(entry: dict, payload: dict) -> None:
    _clear_tags(entry)
    entry.update({"avoid_when": [], "tags": [], "text": None})
    entry.update({k: v for k, v in payload.items() if k in TAG_FIELDS})
    entry["status"] = "tagged"


def tag(root: Path, entry_id: str, payload: object) -> dict:
    errors = validate_payload(payload)
    with index_lock(root):
        index = load_index(root)
        entry = get_entry(index, entry_id)
        if errors:
            raise LibraryError("Invalid tag payload:\n" + "\n".join(f"- {e}" for e in errors))
        _apply_tag(entry, payload)
        save_index(root, index)
    remove_frames(root, entry_id)
    return entry


def tag_batch(root: Path, rows: Sequence[object], lines: Sequence[int] | None = None) -> dict:
    """Tag many entries with one index write. Each row is {"id": ..., <tag fields>}.
    Valid rows are saved; the rest are reported per line and left untouched."""
    lines = lines or range(1, len(rows) + 1)
    checked = []
    for number, row in zip(lines, rows):
        if isinstance(row, BadLine):
            checked.append((number, None, None, [row.error]))
        elif not isinstance(row, dict) or not isinstance(row.get("id"), str):
            checked.append((number, None, None, ["missing 'id' (a string)"]))
        else:
            payload = {k: v for k, v in row.items() if k != "id"}
            checked.append((number, row["id"], payload, validate_payload(payload)))

    tagged: list[str] = []
    rejected: list[dict] = []
    with index_lock(root):
        index = load_index(root)
        seen: set[str] = set()
        for number, entry_id, payload, errors in checked:
            if entry_id is not None and not errors:
                if entry_id in seen:
                    errors = ["duplicate id in this batch"]
                elif entry_id not in index["entries"]:
                    errors = [f"Unknown id: {entry_id}"]
            if entry_id is not None:
                seen.add(entry_id)
            if errors:
                rejected.append({"line": number, "id": entry_id, "errors": errors})
                continue
            _apply_tag(index["entries"][entry_id], payload)
            tagged.append(entry_id)
        if tagged:
            save_index(root, index)
    for entry_id in tagged:
        remove_frames(root, entry_id)
    return {"tagged": tagged, "rejected": rejected}


def review(root: Path, ids: list[str]) -> list[str]:
    with index_lock(root):
        index = load_index(root)
        entries = [get_entry(index, entry_id) for entry_id in ids]
        untagged = [e["id"] for e in entries if e["status"] == "untagged"]
        if untagged:
            raise LibraryError(f"Cannot review untagged entries: {', '.join(untagged)}")
        for entry in entries:
            entry["status"] = "reviewed"
        save_index(root, index)
    return ids


def retag(root: Path, ids: list[str] | None = None, all_entries: bool = False, status: str | None = None) -> list[str]:
    with index_lock(root):
        index = load_index(root)
        if all_entries:
            targets = list(index["entries"].values())
        elif status is not None:
            targets = [e for e in index["entries"].values() if e["status"] == status]
        else:
            targets = [get_entry(index, entry_id) for entry_id in ids or []]
        for entry in targets:
            _clear_tags(entry)
        save_index(root, index)
    return [e["id"] for e in targets]
