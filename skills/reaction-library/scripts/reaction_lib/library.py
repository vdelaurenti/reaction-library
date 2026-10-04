"""Library location, index storage, and shared constants."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

ENV_VAR = "REACTION_LIBRARY"
CATALOG_MAX_ENV = "REACTION_CATALOG_MAX"
DEFAULT_CATALOG_MAX = 300
INDEX_VERSION = 1
STATUSES = ("untagged", "tagged", "reviewed")
TAG_FIELDS = ("description", "humor_mechanisms", "emotions", "use_when", "avoid_when", "tags", "text")
SKILL_DIR = Path(__file__).resolve().parents[2]


class LibraryError(Exception):
    """A user-facing error. The CLI prints it to stderr and exits 1."""


def library_root() -> Path:
    override = os.environ.get(ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".reaction-library"


def catalog_max() -> int:
    """Largest library a brief catalog will print; past it, search is the better first step."""
    value = os.environ.get(CATALOG_MAX_ENV, "")
    try:
        return max(1, int(value)) if value else DEFAULT_CATALOG_MAX
    except ValueError:
        raise LibraryError(f"{CATALOG_MAX_ENV} must be a whole number, not '{value}'.") from None


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


def tree_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def remove_frames(root: Path, entry_id: str) -> int:
    """Delete one entry's frames workdir. Returns the bytes freed."""
    workdir = root / ".frames" / entry_id
    if not workdir.is_dir():
        return 0
    size = tree_size(workdir)
    shutil.rmtree(workdir, ignore_errors=True)
    return size


def stale_frames(root: Path, index: dict) -> list[str]:
    """Frames workdirs no longer needed: the entry is already tagged, or gone from the index."""
    frames_root = root / ".frames"
    if not frames_root.is_dir():
        return []
    entries = index["entries"]
    return sorted(
        p.name for p in frames_root.iterdir()
        if p.is_dir() and entries.get(p.name, {}).get("status") != "untagged"
    )


def clean_frames(root: Path, all_folders: bool = False) -> dict:
    """Remove stale frames workdirs, or every one with all_folders. `frames` recreates them on demand."""
    frames_root = root / ".frames"
    if all_folders:
        targets = sorted(p.name for p in frames_root.iterdir() if p.is_dir()) if frames_root.is_dir() else []
    else:
        targets = stale_frames(root, load_index(root))
    return {"removed": targets, "freed_bytes": sum(remove_frames(root, t) for t in targets)}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
