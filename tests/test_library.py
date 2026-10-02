import re

import pytest

from reaction_lib import library
from reaction_lib.library import LibraryError


def test_library_root_defaults_to_home(monkeypatch, tmp_path):
    monkeypatch.delenv("REACTION_LIBRARY", raising=False)
    monkeypatch.setattr(library.Path, "home", lambda: tmp_path)
    assert library.library_root() == tmp_path / ".reaction-library"


def test_library_root_env_override(lib):
    assert library.library_root() == lib


def test_init_creates_structure_and_is_idempotent(lib):
    library.init_library(lib)
    index = library.load_index(lib)
    assert index == {"version": 1, "entries": {}}
    index["entries"]["x"] = {"id": "x"}
    library.save_index(lib, index)

    library.init_library(lib)

    assert (lib / "media").is_dir()
    assert (lib / ".frames").is_dir()
    assert library.load_index(lib)["entries"] == {"x": {"id": "x"}}


def test_load_index_missing_library(lib):
    with pytest.raises(LibraryError, match="No library"):
        library.load_index(lib)


def test_load_index_corrupt(lib):
    library.init_library(lib)
    (lib / "index.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(LibraryError, match="not valid JSON"):
        library.load_index(lib)


def test_save_index_is_atomic(lib, monkeypatch):
    library.init_library(lib)
    before = (lib / "index.json").read_text(encoding="utf-8")

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(library.os, "replace", boom)
    with pytest.raises(OSError):
        library.save_index(lib, {"version": 1, "entries": {"y": {}}})
    assert (lib / "index.json").read_text(encoding="utf-8") == before


def test_save_index_keeps_non_ascii(lib):
    library.init_library(lib)
    library.save_index(lib, {"version": 1, "entries": {"a": {"text": "café 🔥"}}})
    assert "café 🔥" in (lib / "index.json").read_text(encoding="utf-8")


def test_get_entry_unknown_id(lib):
    library.init_library(lib)
    with pytest.raises(LibraryError, match="Unknown id: nope"):
        library.get_entry(library.load_index(lib), "nope")


def test_entry_path_and_with_path(lib):
    entry = {"id": "abc", "file": "media/abc.gif"}
    assert library.entry_path(lib, entry) == lib / "media" / "abc.gif"
    assert library.with_path(lib, entry) == {**entry, "path": str(lib / "media" / "abc.gif")}


def test_list_entries_filters_by_status(lib):
    library.init_library(lib)
    index = library.load_index(lib)
    index["entries"] = {
        "b": {"id": "b", "original_name": "b.png", "kind": "static", "status": "tagged", "sha256": "x"},
        "a": {"id": "a", "original_name": "a.gif", "kind": "animated", "status": "untagged", "sha256": "y"},
    }
    library.save_index(lib, index)

    assert library.list_entries(lib, status="untagged") == [
        {"id": "a", "original_name": "a.gif", "kind": "animated", "status": "untagged"}
    ]
    assert [e["id"] for e in library.list_entries(lib)] == ["a", "b"]


def test_now_iso_format():
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", library.now_iso())


def test_skill_dir_points_at_skill_folder():
    assert library.SKILL_DIR.name == "reaction-library"
    assert (library.SKILL_DIR / "scripts").is_dir()
