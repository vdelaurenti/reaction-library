"""Validate the model's comedic analysis and manage tag status."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO

from jsonschema import Draft202012Validator

from .library import SKILL_DIR, TAG_FIELDS, LibraryError, get_entry, load_index, save_index

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


def read_payload(source: str, stdin: TextIO | None = None) -> object:
    try:
        if source == "-":
            raw = (stdin or sys.stdin).read()
        else:
            raw = Path(source).read_text(encoding="utf-8-sig")
    except OSError as e:
        raise LibraryError(f"Cannot read payload: {e}") from e
    try:
        return json.loads(raw.lstrip("\ufeff"))
    except json.JSONDecodeError as e:
        raise LibraryError(f"Payload is not valid JSON: {e}") from e


def _clear_tags(entry: dict) -> None:
    for field in TAG_FIELDS:
        entry.pop(field, None)
    entry["status"] = "untagged"


def tag(root: Path, entry_id: str, payload: object) -> dict:
    index = load_index(root)
    entry = get_entry(index, entry_id)
    errors = validate_payload(payload)
    if errors:
        raise LibraryError("Invalid tag payload:\n" + "\n".join(f"- {e}" for e in errors))
    _clear_tags(entry)
    entry.update({"avoid_when": [], "tags": [], "text": None})
    entry.update({k: v for k, v in payload.items() if k in TAG_FIELDS})
    entry["status"] = "tagged"
    save_index(root, index)
    return entry


def review(root: Path, ids: list[str]) -> list[str]:
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
