import io
import json

import pytest
from jsonschema import Draft202012Validator

from reaction_lib import library, media, tagging
from reaction_lib.library import LibraryError


@pytest.fixture
def entry_id(lib, make_png):
    return media.ingest(lib, [make_png()])["added"][0]["id"]


def _entry(lib, entry_id):
    return library.get_entry(library.load_index(lib), entry_id)


def test_vocabulary_has_starter_terms():
    vocab = tagging.load_vocabulary()
    assert len(vocab["humor_mechanisms"]) == 18
    assert len(vocab["emotions"]) == 24
    assert "subverted-expectation" in vocab["humor_mechanisms"]
    assert {"catchphrase", "wordplay", "incongruity"} <= set(vocab["humor_mechanisms"])
    assert {"contentment", "exhaustion", "gratitude"} <= set(vocab["emotions"])


def test_vocabulary_has_no_duplicates_and_no_catch_all_terms():
    vocab = tagging.load_vocabulary()
    for terms in vocab.values():
        assert len(terms) == len(set(terms))
    # "relatable" described nearly every reaction, so it never told two entries apart.
    assert "relatable" not in vocab["humor_mechanisms"]


def test_schema_is_a_valid_json_schema():
    Draft202012Validator.check_schema(tagging.load_schema())


def test_validate_accepts_valid_payload(payload):
    assert tagging.validate_payload(payload) == []


def test_validate_rejects_unknown_terms_and_lists_allowed(payload):
    payload["humor_mechanisms"] = ["Deadpan"]
    errors = tagging.validate_payload(payload)
    assert len(errors) == 1
    assert "unknown term" in errors[0] and "Deadpan" in errors[0]
    assert "deadpan" in errors[0] and "subverted-expectation" in errors[0]


def test_validate_rejects_schema_violations(payload):
    del payload["description"]
    payload["emotions"] = ["joy", "shock", "relief", "panic"]
    payload["tags"] = ["Office"]
    payload["mood"] = "grumpy"
    joined = "\n".join(tagging.validate_payload(payload))
    assert "description" in joined
    assert "emotions" in joined
    assert "tags/0" in joined
    assert "mood" in joined


def test_validate_rejects_non_object():
    assert tagging.validate_payload(["not", "an", "object"])


def test_tag_sets_fields_and_status(lib, entry_id, payload):
    entry = tagging.tag(lib, entry_id, payload)
    assert entry["status"] == "tagged"
    stored = _entry(lib, entry_id)
    for field in library.TAG_FIELDS:
        assert stored[field] == payload[field]


def test_tag_fills_optional_defaults(lib, entry_id, payload):
    for field in ("avoid_when", "tags", "text"):
        del payload[field]
    tagging.tag(lib, entry_id, payload)
    stored = _entry(lib, entry_id)
    assert stored["avoid_when"] == [] and stored["tags"] == [] and stored["text"] is None


def test_invalid_tag_leaves_entry_untouched(lib, entry_id, payload):
    before = _entry(lib, entry_id)
    payload["emotions"] = ["hangry"]
    with pytest.raises(LibraryError, match="Invalid tag payload"):
        tagging.tag(lib, entry_id, payload)
    assert _entry(lib, entry_id) == before


def test_tag_unknown_id(lib, entry_id, payload):
    with pytest.raises(LibraryError, match="Unknown id"):
        tagging.tag(lib, "nope", payload)


def test_review_then_retag_moves_back_to_tagged(lib, entry_id, payload):
    tagging.tag(lib, entry_id, payload)
    assert tagging.review(lib, [entry_id]) == [entry_id]
    assert _entry(lib, entry_id)["status"] == "reviewed"
    tagging.tag(lib, entry_id, payload)
    assert _entry(lib, entry_id)["status"] == "tagged"


def test_review_rejects_untagged_and_changes_nothing(lib, entry_id, make_png, payload):
    tagged_id = media.ingest(lib, [make_png()])["added"][0]["id"]
    tagging.tag(lib, tagged_id, payload)
    with pytest.raises(LibraryError, match=entry_id):
        tagging.review(lib, [tagged_id, entry_id])
    assert _entry(lib, tagged_id)["status"] == "tagged"


def test_retag_selectors(lib, make_png, payload):
    ids = [media.ingest(lib, [make_png()])["added"][0]["id"] for _ in range(3)]
    for entry_id in ids:
        tagging.tag(lib, entry_id, payload)
    tagging.review(lib, [ids[0]])

    assert tagging.retag(lib, status="reviewed") == [ids[0]]
    assert "description" not in _entry(lib, ids[0])
    assert _entry(lib, ids[0])["status"] == "untagged"

    assert tagging.retag(lib, ids=[ids[1]]) == [ids[1]]
    assert sorted(tagging.retag(lib, all_entries=True)) == sorted(ids)
    assert all(_entry(lib, i)["status"] == "untagged" for i in ids)


def test_read_payload_from_file_with_bom(tmp_path, payload):
    path = tmp_path / "tag.json"
    path.write_text(json.dumps(payload), encoding="utf-8-sig")
    assert tagging.read_payload(str(path)) == payload


def test_read_payload_from_stdin(payload):
    stdin = io.StringIO("\ufeff" + json.dumps(payload))
    assert tagging.read_payload("-", stdin=stdin) == payload


def test_read_payload_errors(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    with pytest.raises(LibraryError, match="not valid JSON"):
        tagging.read_payload(str(bad))
    with pytest.raises(LibraryError, match="Cannot read payload"):
        tagging.read_payload(str(tmp_path / "missing.json"))


def test_read_payload_from_utf16_file(tmp_path, payload):
    """Windows PowerShell 5.1 `Out-File` and `>` write UTF-16LE with a BOM."""
    payload["text"] = "café"
    path = tmp_path / "tag.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-16")
    assert tagging.read_payload(str(path)) == payload


def test_read_payload_non_utf8_file_is_a_clear_error(tmp_path):
    path = tmp_path / "ansi.json"
    path.write_bytes('{"text": "café"}'.encode("cp1252"))
    with pytest.raises(LibraryError, match="UTF-8"):
        tagging.read_payload(str(path))
