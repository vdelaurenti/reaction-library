import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from reaction_lib import cli

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "reaction-library" / "scripts" / "reaction_library.py"


@pytest.fixture
def run(capsys):
    def _run(*args):
        code = cli.main([str(a) for a in args])
        out, err = capsys.readouterr()
        return code, out, err

    return _run


def _json(out):
    return json.loads(out)


def _ingest_one(run, path):
    code, out, _ = run("ingest", path)
    assert code == 0
    return _json(out)["added"][0]["id"]


def test_init(run, lib):
    code, out, _ = run("init")
    assert code == 0 and _json(out) == {"library": str(lib)}


def test_ingest_list_frames_tag_get(run, lib, make_gif, tmp_path, payload):
    entry_id = _ingest_one(run, make_gif())

    code, out, _ = run("list", "--status", "untagged")
    assert [e["id"] for e in _json(out)] == [entry_id]

    code, out, _ = run("frames", entry_id)
    frames = _json(out)
    assert code == 0 and len(frames["frames"]) == 3

    payload_file = Path(frames["workdir"]) / "tag.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")
    code, out, _ = run("tag", entry_id, payload_file)
    assert code == 0 and _json(out)["status"] == "tagged"

    code, out, _ = run("get", entry_id)
    got = _json(out)
    assert got["description"] == payload["description"]
    assert got["path"] == str(lib / "media" / f"{entry_id}.gif")


def test_tag_from_stdin(run, lib, make_png, payload, monkeypatch):
    entry_id = _ingest_one(run, make_png())
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    code, out, _ = run("tag", entry_id, "-")
    assert code == 0 and _json(out)["status"] == "tagged"


def test_invalid_tag_reports_problems(run, lib, make_png, tmp_path, payload):
    entry_id = _ingest_one(run, make_png())
    payload["emotions"] = ["hangry"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")

    code, out, err = run("tag", entry_id, bad)

    assert code == 1 and out == ""
    assert "Invalid tag payload" in err and "hangry" in err and "exasperation" in err


def test_review_retag_and_selector_errors(run, lib, make_png, tmp_path, payload):
    entry_id = _ingest_one(run, make_png())
    payload_file = tmp_path / "p.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")
    run("tag", entry_id, payload_file)

    code, out, _ = run("review", entry_id)
    assert code == 0 and _json(out) == {"reviewed": [entry_id]}

    code, _, err = run("retag")
    assert code == 1 and "exactly one of" in err
    code, _, err = run("retag", entry_id, "--all")
    assert code == 1

    code, out, _ = run("retag", "--status", "reviewed")
    assert code == 0 and _json(out) == {"untagged": [entry_id]}


def test_search_and_catalog(run, lib, make_png, tmp_path, payload):
    entry_id = _ingest_one(run, make_png())
    payload_file = tmp_path / "p.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")
    run("tag", entry_id, payload_file)

    code, out, _ = run("search", "deploy fails", "--emotion", "exasperation", "--limit", "3")
    result = _json(out)
    assert code == 0 and result["query"] == "deploy fails"
    assert [r["id"] for r in result["results"]] == [entry_id]
    assert result["total_matches"] == 1

    code, out, _ = run("search", "deploy fails", "--exclude", f"{entry_id},other")
    assert _json(out)["results"] == [] and _json(out)["total_matches"] == 0

    code, out, _ = run("catalog", "--kind", "static")
    header, line = out.splitlines()
    assert code == 0 and header == f"# library: {lib}"
    assert line.startswith(f"{entry_id} | static | media/{entry_id}.png | ")

    code, out, _ = run("catalog", "--kind", "animated")
    assert out.strip() == "(no tagged entries)"


def _tag_pngs(run, make_png, tmp_path, payload, count, **fields):
    payload_file = tmp_path / "p.json"
    payload_file.write_text(json.dumps({**payload, **fields}), encoding="utf-8")
    ids = []
    for _ in range(count):
        entry_id = _ingest_one(run, make_png())
        run("tag", entry_id, payload_file)
        ids.append(entry_id)
    return ids


def test_search_output_is_brief_unless_full(run, lib, make_png, tmp_path, payload):
    [entry_id] = _tag_pngs(run, make_png, tmp_path, payload, 1)

    code, out, _ = run("search", "deploy")
    [result] = _json(out)["results"]
    assert "sha256" not in result and result["id"] == entry_id and "avoid_when" in result

    code, out, _ = run("search", "deploy", "--format", "full")
    assert "sha256" in _json(out)["results"][0]


def test_search_default_limit_is_fifteen(run, lib, make_png, tmp_path, payload):
    _tag_pngs(run, make_png, tmp_path, payload, 16)
    code, out, _ = run("search", "deploy")
    assert len(_json(out)["results"]) == 15 and _json(out)["total_matches"] == 16


def test_brief_catalog_header_and_size_limit(run, lib, make_png, tmp_path, payload, monkeypatch):
    _tag_pngs(run, make_png, tmp_path, payload, 3)

    code, out, _ = run("catalog", "--brief")
    lines = out.splitlines()
    assert code == 0 and lines[0] == f"# library: {lib} | 3 entries | file | description | emotions | use_when"
    assert len(lines) == 4

    code, out, _ = run("catalog", "--brief", "--max", "2")
    assert code == 0 and out.startswith("# too many entries for a brief catalog: 3 match, limit 2.")
    assert "search" in out and "--emotion" in out

    monkeypatch.setenv("REACTION_CATALOG_MAX", "2")
    code, out, _ = run("catalog", "--brief")
    assert out.startswith("# too many entries")
    code, out, _ = run("catalog", "--brief", "--kind", "animated")
    assert out.strip() == "(no tagged entries)"


def test_search_unknown_filter_term_lists_allowed(run, lib):
    run("init")
    code, _, err = run("search", "x", "--humor", "puns")
    assert code == 1 and "puns" in err and "deadpan" in err


def test_search_limit_must_be_positive(run, lib):
    with pytest.raises(SystemExit) as exc:
        run("search", "x", "--limit", "0")
    assert exc.value.code == 2


def test_catalog_empty_and_unknown_id(run, lib):
    run("init")
    code, out, _ = run("catalog")
    assert code == 0 and out.strip() == "(no tagged entries)"
    code, _, err = run("get", "nope")
    assert code == 1 and "Unknown id: nope" in err


def test_rebuild_and_doctor(run, lib, make_png):
    run("ingest", make_png())
    code, out, _ = run("rebuild")
    assert code == 0 and _json(out)["missing"] == []
    code, out, _ = run("doctor")
    assert "Library:" in out
    assert code in (0, 1)


def test_entry_script_prints_utf8(lib, make_png, tmp_path, payload):
    """Runs the real entry script in a subprocess with no UTF-8 env hints; Windows consoles default to cp1252."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env["REACTION_LIBRARY"] = str(lib)

    def call(*args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, env=env)

    added = call("ingest", make_png())
    assert added.returncode == 0, added.stderr
    entry_id = json.loads(added.stdout.decode("utf-8"))["added"][0]["id"]
    payload["text"] = "café 🔥"
    payload_file = tmp_path / "p.json"
    payload_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert call("tag", entry_id, payload_file).returncode == 0

    got = call("get", entry_id)

    assert got.returncode == 0, got.stderr
    assert json.loads(got.stdout.decode("utf-8"))["text"] == "café 🔥"


def test_clean_frames(run, lib, make_gif):
    entry_id = _ingest_one(run, make_gif())
    run("frames", entry_id)

    code, out, _ = run("clean-frames")
    assert code == 0 and _json(out)["removed"] == []

    code, out, _ = run("clean-frames", "--all")
    assert code == 0 and _json(out)["removed"] == [entry_id]
