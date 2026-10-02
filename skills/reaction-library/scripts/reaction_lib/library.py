"""Library location, index storage, and shared constants."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

ENV_VAR = "REACTION_LIBRARY"
INDEX_VERSION = 1
STATUSES = ("untagged", "tagged", "reviewed")
TAG_FIELDS = ("description", "humor_mechanisms", "emotions", "use_when", "avoid_when", "tags", "text")
SKILL_DIR = Path(__file__).resolve().parents[2]


class LibraryError(Exception):
    """A user-facing error. The CLI prints it to stderr and exits 1."""


def library_root() -> Path:
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".reaction-library"


def init_library(root: Path) -> Path:
    (root / "media").mkdir(parents=True, exist_ok=True)
    (root / ".frames").mkdir(exist_ok=True)
    if not (root / "index.json").exists():
        save_index(root, {"version": INDEX_VERSION, "entries": {}})
    return root


def load_index(root: Path) -> dict:
    path = root / "index.json"
    if not path.exists():
        raise LibraryError(f"No library at {root}. Run `init` or `ingest` first.")
    try:
        index = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise LibraryError(f"index.json is not valid JSON: {e}") from e
    if not isinstance(index, dict) or not isinstance(index.get("entries"), dict):
        raise LibraryError("index.json is missing its 'entries' object.")
    return index


def save_index(root: Path, index: dict) -> None:
    """Write to a temp file, then atomically replace index.json (atomic on every OS)."""
    tmp = root / "index.json.tmp"
    tmp.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, root / "index.json")


def get_entry(index: dict, entry_id: str) -> dict:
    try:
        return index["entries"][entry_id]
    except KeyError:
        raise LibraryError(f"Unknown id: {entry_id}") from None


def entry_path(root: Path, entry: dict) -> Path:
    return root.joinpath(*entry["file"].split("/"))


def with_path(root: Path, entry: dict) -> dict:
    return {**entry, "path": str(entry_path(root, entry))}


def list_entries(root: Path, status: str | None = None) -> list[dict]:
    entries = load_index(root)["entries"].values()
    return [
        {k: e[k] for k in ("id", "original_name", "kind", "status")}
        for e in sorted(entries, key=lambda e: e["id"])
        if status is None or e["status"] == status
    ]


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
