import pytest

from reaction_lib import doctor, library, media


@pytest.fixture(autouse=True)
def uv_on_path(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: "/usr/local/bin/uv")


def test_healthy_library(lib, make_png):
    media.ingest(lib, [make_png()])

    lines, ok = doctor.run_doctor(lib)

    text = "\n".join(lines)
    assert ok, text
    assert "[FAIL]" not in text and "[warn]" not in text
    assert f"Library: {lib} (from REACTION_LIBRARY)" in text
    assert "1 entries (1 untagged, 0 tagged, 0 reviewed)" in text


def test_missing_library_suggests_init(lib):
    lines, ok = doctor.run_doctor(lib)
    assert not ok
    assert any(line.startswith("[FAIL] library exists") and "init" in line for line in lines)


def test_missing_uv_fails(lib, monkeypatch):
    library.init_library(lib)
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    lines, ok = doctor.run_doctor(lib)
    assert not ok
    assert any(line.startswith("[FAIL] uv on PATH") for line in lines)


def test_corrupt_index_fails(lib):
    library.init_library(lib)
    (lib / "index.json").write_text("{", encoding="utf-8")
    lines, ok = doctor.run_doctor(lib)
    assert not ok
    assert any(line.startswith("[FAIL] index.json") for line in lines)


def test_inconsistency_is_a_warning(lib, make_png):
    entry_id = media.ingest(lib, [make_png()])["added"][0]["id"]
    (lib / "media" / f"{entry_id}.png").unlink()

    lines, ok = doctor.run_doctor(lib)

    assert ok
    assert any(line.startswith("[warn]") and "1 missing" in line and "rebuild" in line for line in lines)


def test_missing_media_folder_is_reported(lib, make_png):
    media.ingest(lib, [make_png()])
    (lib / "media" / next(p.name for p in (lib / "media").iterdir())).unlink()
    (lib / "media").rmdir()

    lines, ok = doctor.run_doctor(lib)

    assert not ok
    assert any(line.startswith("[FAIL] media/ exists") and "rebuild" in line for line in lines)
