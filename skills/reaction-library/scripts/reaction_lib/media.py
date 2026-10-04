"""Bring media into the library and inspect it."""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Iterator
from pathlib import Path

from PIL import Image, ImageDraw

from .library import LibraryError, entry_path, index_lock, init_library, load_index, now_iso, save_index

SUPPORTED_EXTS = frozenset({".gif", ".png", ".jpg", ".jpeg", ".webp"})
ID_LEN = 10
MAX_FRAMES = 4
SHEET_TILE_WIDTH = 384
SHEET_GAP = 4
STATIC_MAX_EDGE = 768


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
    with index_lock(root):
        return _ingest(root, paths, move)


def _ingest(root: Path, paths: list[Path], move: bool) -> dict:
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


def keyframe_indices(n_frames: int, k: int = MAX_FRAMES) -> list[int]:
    """Up to k evenly spaced frame indices, always including the first and last."""
    if n_frames <= k:
        return list(range(n_frames))
    return sorted({round(i * (n_frames - 1) / (k - 1)) for i in range(k)})


def _keyframes(src: Path) -> list[Image.Image]:
    with Image.open(src) as im:
        frames = []
        for index in keyframe_indices(im.n_frames):
            im.seek(index)
            frames.append(im.convert("RGB"))
    return frames


def contact_sheet(frames: list[Image.Image]) -> Image.Image:
    """Keyframes in playback order: 2x2 for four, one row otherwise. Tiles are at most
    SHEET_TILE_WIDTH wide (never upscaled) and numbered in their top-left corner."""
    w, h = frames[0].size
    tile_w = min(w, SHEET_TILE_WIDTH)
    tile_h = max(1, round(h * tile_w / w))
    cols, rows = (2, 2) if len(frames) == 4 else (len(frames), 1)
    sheet = Image.new("RGB", (cols * tile_w + (cols - 1) * SHEET_GAP, rows * tile_h + (rows - 1) * SHEET_GAP),
                      (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    for n, frame in enumerate(frames):
        x, y = (n % cols) * (tile_w + SHEET_GAP), (n // cols) * (tile_h + SHEET_GAP)
        sheet.paste(frame.resize((tile_w, tile_h)), (x, y))
        draw.rectangle((x, y, x + 11, y + 13), fill=(0, 0, 0))
        draw.text((x + 3, y + 1), str(n + 1), fill=(255, 255, 255))
    return sheet


def extract_frames(root: Path, entry: dict, separate: bool = False) -> dict:
    """One contact sheet for the model to look at, or with separate=True each keyframe on its own."""
    src = entry_path(root, entry)
    if not src.exists():
        raise LibraryError(f"Media file missing for {entry['id']} ({entry['file']}). Run `rebuild`.")
    workdir = root / ".frames" / entry["id"]
    workdir.mkdir(parents=True, exist_ok=True)
    for old in [*workdir.glob("frame-*.png"), workdir / "sheet.png"]:
        old.unlink(missing_ok=True)
    if entry["kind"] == "static":
        with Image.open(src) as im:
            too_big = max(im.size) > STATIC_MAX_EDGE
            if too_big:
                small = im.convert("RGB")
                small.thumbnail((STATIC_MAX_EDGE, STATIC_MAX_EDGE))
        if too_big:
            small.save(workdir / "sheet.png")
            frames = [workdir / "sheet.png"]
        else:
            frames = [src]
    elif separate:
        frames = []
        for n, frame in enumerate(_keyframes(src)):
            frame.save(workdir / f"frame-{n}.png")
            frames.append(workdir / f"frame-{n}.png")
    else:
        contact_sheet(_keyframes(src)).save(workdir / "sheet.png")
        frames = [workdir / "sheet.png"]
    return {"id": entry["id"], "workdir": str(workdir), "frames": [str(p) for p in frames]}


def extract_many(root: Path, ids: list[str], separate: bool = False) -> list[dict]:
    """extract_frames for each id; a bad id gets an error entry instead of failing the batch."""
    entries = load_index(root)["entries"]
    results = []
    for entry_id in ids:
        try:
            if entry_id not in entries:
                raise LibraryError(f"Unknown id: {entry_id}")
            results.append(extract_frames(root, entries[entry_id], separate=separate))
        except LibraryError as e:
            results.append({"id": entry_id, "error": str(e)})
    return results


def rebuild(root: Path, prune: bool = False, dry_run: bool = False) -> dict:
    """Reconcile index.json with media/. Existing tags are never touched."""
    if dry_run:
        return _rebuild(root, prune, dry_run)
    with index_lock(root):
        return _rebuild(root, prune, dry_run)


def _rebuild(root: Path, prune: bool, dry_run: bool) -> dict:
    index = load_index(root)
    entries = index["entries"]
    known = {e["file"] for e in entries.values()}
    by_sha = {e["sha256"]: entry_id for entry_id, e in entries.items()}
    report: dict[str, list] = {"added": [], "missing": [], "pruned": [], "skipped": []}

    media_dir = root / "media"
    if not media_dir.is_dir() and not dry_run:
        media_dir.mkdir(parents=True)
    for path in sorted(media_dir.iterdir()) if media_dir.is_dir() else []:
        if not path.is_file() or path.name.startswith(".") or f"media/{path.name}" in known:
            continue
        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTS:
            report["skipped"].append({"path": str(path), "reason": f"unsupported type {ext or '(no extension)'}"})
            continue
        try:
            kind = detect_kind(path)
        except LibraryError as e:
            report["skipped"].append({"path": str(path), "reason": str(e)})
            continue
        sha = sha256_file(path)
        if sha in by_sha:
            report["skipped"].append({"path": str(path), "reason": f"duplicate of {by_sha[sha]}"})
            continue
        entry_id = assign_id(sha, entries)
        by_sha[sha] = entry_id
        report["added"].append({"id": entry_id, "path": str(path)})
        if not dry_run:
            entries[entry_id] = make_entry(entry_id, f"media/{path.name}", path.name, sha, kind)

    report["missing"] = sorted(i for i, e in entries.items() if not entry_path(root, e).exists())
    if prune:
        report["pruned"] = list(report["missing"])
        if not dry_run:
            for entry_id in report["pruned"]:
                del entries[entry_id]
                shutil.rmtree(root / ".frames" / entry_id, ignore_errors=True)

    if not dry_run:
        save_index(root, index)
    return report
