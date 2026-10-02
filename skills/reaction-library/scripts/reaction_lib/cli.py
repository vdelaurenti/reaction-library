"""Command-line interface. Every command prints JSON except `catalog` and `doctor`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .library import STATUSES, LibraryError, get_entry, init_library, library_root, list_entries, load_index, with_path


def configure_utf8() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def emit(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


def cmd_init(root: Path, args: argparse.Namespace) -> int:
    emit({"library": str(init_library(root))})
    return 0


def cmd_ingest(root: Path, args: argparse.Namespace) -> int:
    from .media import ingest

    emit(ingest(root, [Path(p) for p in args.paths], move=args.move))
    return 0


def cmd_list(root: Path, args: argparse.Namespace) -> int:
    emit(list_entries(root, status=args.status))
    return 0


def cmd_frames(root: Path, args: argparse.Namespace) -> int:
    from .media import extract_frames

    emit(extract_frames(root, get_entry(load_index(root), args.id)))
    return 0


def cmd_tag(root: Path, args: argparse.Namespace) -> int:
    from .tagging import read_payload, tag

    emit(with_path(root, tag(root, args.id, read_payload(args.payload))))
    return 0


def cmd_review(root: Path, args: argparse.Namespace) -> int:
    from .tagging import review

    emit({"reviewed": review(root, args.ids)})
    return 0


def cmd_retag(root: Path, args: argparse.Namespace) -> int:
    from .tagging import retag

    if sum([bool(args.ids), args.all, args.status is not None]) != 1:
        raise LibraryError("retag needs exactly one of: ids, --all, or --status")
    emit({"untagged": retag(root, ids=args.ids, all_entries=args.all, status=args.status)})
    return 0


def cmd_rebuild(root: Path, args: argparse.Namespace) -> int:
    from .media import rebuild

    emit(rebuild(root, prune=args.prune))
    return 0


def cmd_search(root: Path, args: argparse.Namespace) -> int:
    from .search import search
    from .tagging import load_vocabulary

    vocab = load_vocabulary()
    for field, value in (("humor_mechanisms", args.humor), ("emotions", args.emotion)):
        if value is not None and value not in vocab[field]:
            raise LibraryError(f"Unknown {field} term '{value}'. Allowed: {', '.join(vocab[field])}")
    results = search(root, args.query, humor=args.humor, emotion=args.emotion, kind=args.kind, limit=args.limit)
    emit({"query": args.query, "results": results})
    return 0


def cmd_get(root: Path, args: argparse.Namespace) -> int:
    emit(with_path(root, get_entry(load_index(root), args.id)))
    return 0


def cmd_catalog(root: Path, args: argparse.Namespace) -> int:
    from .search import catalog_lines

    lines = catalog_lines(root)
    print("\n".join(lines) if lines else "(no tagged entries)")
    return 0


def cmd_doctor(root: Path, args: argparse.Namespace) -> int:
    from .doctor import run_doctor

    lines, ok = run_doctor(root)
    print("\n".join(lines))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reaction_library", description="Tag and retrieve reaction GIFs and memes.")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, handler, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(handler=handler)
        return p

    add("init", cmd_init, "create the library folder")
    p = add("ingest", cmd_ingest, "copy files or folders into the library")
    p.add_argument("paths", nargs="+")
    p.add_argument("--move", action="store_true", help="delete each source after a successful copy")
    p = add("list", cmd_list, "list entries")
    p.add_argument("--status", choices=STATUSES)
    p = add("frames", cmd_frames, "extract keyframes for tagging")
    p.add_argument("id")
    p = add("tag", cmd_tag, "save a tag payload (JSON file path, or - for stdin)")
    p.add_argument("id")
    p.add_argument("payload")
    p = add("review", cmd_review, "mark tagged entries as reviewed")
    p.add_argument("ids", nargs="+")
    p = add("retag", cmd_retag, "clear tags so entries get re-tagged")
    p.add_argument("ids", nargs="*")
    p.add_argument("--all", action="store_true")
    p.add_argument("--status", choices=STATUSES)
    p = add("rebuild", cmd_rebuild, "reconcile the index with media/")
    p.add_argument("--prune", action="store_true", help="drop entries whose files are missing")
    p = add("search", cmd_search, "find reactions for a moment")
    p.add_argument("query")
    p.add_argument("--humor")
    p.add_argument("--emotion")
    p.add_argument("--kind", choices=("animated", "static"))
    p.add_argument("--limit", type=_positive_int, default=5)
    p = add("get", cmd_get, "show one entry")
    p.add_argument("id")
    add("catalog", cmd_catalog, "one line per tagged entry")
    add("doctor", cmd_doctor, "check the environment and library")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.handler(library_root(), args)
    except LibraryError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
