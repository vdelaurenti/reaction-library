"""Check the environment and library. Imports only the standard library up front,
so it still runs when a third-party dependency is missing."""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import sys
from collections import Counter
from pathlib import Path

from .library import ENV_VAR, SKILL_DIR, STATUSES, LibraryError, load_index


def _writable(root: Path) -> bool:
    probe = root / ".doctor-probe"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def run_doctor(root: Path) -> tuple[list[str], bool]:
    lines: list[str] = []
    ok = True

    def check(passed: bool, label: str, hint: str = "", fatal: bool = True) -> bool:
        nonlocal ok
        if passed:
            lines.append(f"[ok] {label}")
        else:
            ok = ok and not fatal
            lines.append(f"[{'FAIL' if fatal else 'warn'}] {label}" + (f" -> {hint}" if hint else ""))
        return passed

    lines.append(f"OS: {platform.system()} {platform.release()} ({platform.machine()})")
    check(sys.version_info >= (3, 11), f"Python {platform.python_version()} (need >= 3.11)",
          "run through `uv run`, which provides a suitable Python")
    uv = shutil.which("uv")
    check(uv is not None, f"uv on PATH: {uv or 'not found'}",
          "install uv: https://docs.astral.sh/uv/getting-started/installation/")
    deps_ok = True
    for module in ("PIL", "jsonschema"):
        deps_ok &= check(importlib.util.find_spec(module) is not None, f"{module} importable",
                         "run through `uv run` so dependencies are installed")
    for name in ("vocabulary.json", "schema.json", "synonyms.json"):
        try:
            json.loads((SKILL_DIR / name).read_text(encoding="utf-8"))
            check(True, f"{name} parses")
        except (OSError, json.JSONDecodeError) as e:
            check(False, f"{name} parses: {e}", "reinstall the skill")

    source = f"from {ENV_VAR}" if os.environ.get(ENV_VAR) else "default"
    lines.append(f"Library: {root} ({source})")
    if not check(root.is_dir(), "library exists", "run `init`, or just `ingest` some files"):
        return lines, ok
    check(_writable(root), "library is writable", "check the folder's permissions")
    try:
        index = load_index(root)
    except LibraryError as e:
        check(False, f"index.json: {e}", "move index.json aside, run `init`, then `rebuild` (tags will be lost)")
        return lines, ok
    check((root / "media").is_dir(), "media/ exists", "run `rebuild` to recreate it and see which entries lost their files")
    counts = Counter(e.get("status") for e in index["entries"].values())
    summary = ", ".join(f"{counts[s]} {s}" for s in STATUSES)
    check(True, f"index.json: {len(index['entries'])} entries ({summary})")

    try:
        vocab = json.loads((SKILL_DIR / "vocabulary.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        vocab = None
    if vocab is not None:
        stale = sorted(
            e["id"] for e in index["entries"].values()
            if any(t not in vocab[f] for f in ("humor_mechanisms", "emotions") for t in e.get(f, []))
        )
        shown = ", ".join(stale[:10]) + (", ..." if len(stale) > 10 else "")
        check(not stale, f"tags use current vocabulary: {len(stale)} entries use retired terms" + (f" ({shown})" if stale else ""),
              "re-tag them; `retag <id ...>` clears their tags", fatal=False)

    if deps_ok:
        from .media import rebuild

        report = rebuild(root, dry_run=True)
        consistent = not report["added"] and not report["missing"]
        check(consistent,
              f"index matches media/: {len(report['added'])} untracked, {len(report['missing'])} missing",
              "run `rebuild` (add --prune to drop missing entries)", fatal=False)
    return lines, ok
