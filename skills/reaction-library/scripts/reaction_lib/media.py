"""Bring media into the library and inspect it."""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Iterator
from pathlib import Path

from PIL import Image

from .library import LibraryError, init_library, load_index, now_iso, save_index

SUPPORTED_EXTS = frozenset({".gif", ".png", ".jpg", ".jpeg", ".webp"})
ID_LEN = 10


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_kind(path: Path) -> str:
    """Return 'animated' or 'static' based on the content, not the file name."""
    try:
        with Image.open(path) as im:
            frames = getattr(im, "n_frames", 1)
            im.load()
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as e:
        raise LibraryError(f"Not a readable image: {e}") from e
    return "animated" if frames > 1 else "static"


def assign_id(sha: str, entries: dict) -> str:
    length = ID_LEN
    while sha[:length] in entries:
        length += 2
    return sha[:length]


def make_entry(entry_id: str, file: str, original_name: str, sha: str, kind: str) -> dict:
    return {
        "id": entry_id,
        "file": file,
        "original_name": original_name,
        "sha256": sha,
        "kind": kind,
        "added_at": now_iso(),
        "status": "untagged",
    }


def _candidates(paths: list[Path]) -> Iterator[Path]:
    for path in paths:
        if path.is_dir():
            yield from sorted(
                p for p in path.rglob("*")
                if p.is_file() and not any(part.startswith(".") for part in p.relative_to(path).parts)
            )
        else:
            yield path


def ingest(root: Path, paths: list[Path], move: bool = False) -> dict:
    init_library(root)
    index = load_index(root)
    entries = index["entries"]
    by_sha = {e["sha256"]: entry_id for entry_id, e in entries.items()}
    report: dict[str, list] = {"added": [], "duplicates": [], "skipped": []}

    for src in _candidates(paths):
        if not src.is_file():
            report["skipped"].append({"path": str(src), "reason": "not found"})
            continue
        ext = src.suffix.lower()
        if ext not in SUPPORTED_EXTS:
            report["skipped"].append({"path": str(src), "reason": f"unsupported type {ext or '(no extension)'}"})
            continue
        try:
            kind = detect_kind(src)
        except LibraryError as e:
            report["skipped"].append({"path": str(src), "reason": str(e)})
            continue
        sha = sha256_file(src)
        if sha in by_sha:
            # Never delete a duplicate's source, even with --move.
            report["duplicates"].append({"path": str(src), "id": by_sha[sha]})
            continue
        entry_id = assign_id(sha, entries)
        dest = root / "media" / f"{entry_id}{ext}"
        try:
            shutil.copy2(src, dest)
            if move:
                src.unlink()
        except OSError as e:
            report["skipped"].append({"path": str(src), "reason": f"copy failed: {e}"})
            continue
        entries[entry_id] = make_entry(entry_id, f"media/{dest.name}", src.name, sha, kind)
        by_sha[sha] = entry_id
        save_index(root, index)
        report["added"].append({"id": entry_id, "path": str(src), "kind": kind})

    return report
