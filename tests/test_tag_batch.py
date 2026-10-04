import io
import json
import sys

import pytest

from reaction_lib import cli, library, media, tagging


@pytest.fixture
def ids(lib, make_gif):
    return [media.ingest(lib, [make_gif()])["added"][0]["id"] for _ in range(3)]


def _line(entry_id, payload, **changes):
    return json.dumps({"id": entry_id, **payload, **changes})


def _write(tmp_path, lines):
    path = tmp_path / "batch.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _status(lib, entry_id):
    return library.load_index(lib)["entries"][entry_id]["status"]


def test_all_valid_lines_are_saved_in_one_write(lib, ids, payload, monkeypatch):
    writes = []
    real_save = library.save_index
    monkeypatch.setattr(tagging, "save_index", lambda root, index: (writes.append(1), real_save(root, index)))

    result = tagging.tag_batch(lib, [json.loads(_line(i, payload)) for i in ids])

    assert result == {"tagged": ids, "rejected": []}
    assert len(writes) == 1
    assert all(_status(lib, i) == "tagged" for i in ids)


def test_invalid_lines_are_rejected_and_valid_ones_still_saved(lib, ids, payload):
    good, bad, _ = ids
    result = tagging.tag_batch(lib, [json.loads(_line(good, payload)), json.loads(_line(bad, payload, emotions=["hangry"]))])

    assert result["tagged"] == [good]
    [rejected] = result["rejected"]
    assert rejected["id"] == bad and rejected["line"] == 2 and "hangry" in rejected["errors"][0]
    assert _status(lib, bad) == "untagged"


def test_unknown_missing_and_duplicate_ids_are_rejected(lib, ids, payload):
    first = ids[0]
    rows = [json.loads(_line(first, payload)), json.loads(_line("nope", payload)), payload, json.loads(_line(first, payload))]

    result = tagging.tag_batch(lib, rows)

    assert result["tagged"] == [first]
    reasons = {r["line"]: r["errors"][0] for r in result["rejected"]}
    assert "Unknown id" in reasons[2]
    assert "missing 'id'" in reasons[3]
    assert "duplicate" in reasons[4]


def test_frames_removed_only_for_saved_entries(lib, ids, payload):
    good, bad, _ = ids
    for entry_id in (good, bad):
        media.extract_frames(lib, library.get_entry(library.load_index(lib), entry_id))

    tagging.tag_batch(lib, [json.loads(_line(good, payload)), json.loads(_line(bad, payload, emotions=[]))])

    assert not (lib / ".frames" / good).exists()
    assert (lib / ".frames" / bad).is_dir()


def test_read_jsonl_skips_blank_lines_and_reports_bad_json(tmp_path, payload):
    path = tmp_path / "b.jsonl"
    path.write_text(_line("a", payload) + "\n\n{not json\n", encoding="utf-8")

    rows = tagging.read_jsonl(str(path))

    assert rows[0][0] == 1 and rows[0][1]["id"] == "a"
    assert rows[1][0] == 3 and isinstance(rows[1][1], tagging.BadLine)


def test_cli_tag_batch_file_and_exit_codes(lib, ids, payload, tmp_path, capsys):
    path = _write(tmp_path, [_line(ids[0], payload), "{oops"])

    code = cli.main(["tag-batch", str(path)])
    out = json.loads(capsys.readouterr().out)

    assert code == 1
    assert out["tagged"] == [ids[0]]
    assert out["rejected"][0]["line"] == 2 and "not valid JSON" in out["rejected"][0]["errors"][0]

    path = _write(tmp_path, [_line(ids[1], payload)])
    assert cli.main(["tag-batch", str(path)]) == 0


def test_cli_tag_batch_from_stdin(lib, ids, payload, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO(_line(ids[0], payload) + "\n"))

    code = cli.main(["tag-batch", "-"])

    assert code == 0 and json.loads(capsys.readouterr().out)["tagged"] == [ids[0]]
