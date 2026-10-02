import shutil

from reaction_lib import library, media, tagging


def test_rebuild_adds_untracked_files_and_keeps_tags(lib, make_png, payload):
    tagged_id = media.ingest(lib, [make_png()])["added"][0]["id"]
    tagging.tag(lib, tagged_id, payload)
    stray = make_png("dropped-in.png")
    shutil.copy2(stray, lib / "media" / "dropped-in.png")

    report = media.rebuild(lib)

    assert len(report["added"]) == 1 and report["missing"] == []
    entries = library.load_index(lib)["entries"]
    new = entries[report["added"][0]["id"]]
    assert new["file"] == "media/dropped-in.png"
    assert new["original_name"] == "dropped-in.png"
    assert new["status"] == "untagged" and new["kind"] == "static"
    assert entries[tagged_id]["description"] == payload["description"]


def test_rebuild_reports_missing_without_prune(lib, make_png):
    entry_id = media.ingest(lib, [make_png()])["added"][0]["id"]
    (lib / "media" / f"{entry_id}.png").unlink()

    report = media.rebuild(lib)

    assert report["missing"] == [entry_id] and report["pruned"] == []
    assert entry_id in library.load_index(lib)["entries"]


def test_rebuild_prune_removes_entry_and_frames(lib, make_gif):
    entry_id = media.ingest(lib, [make_gif()])["added"][0]["id"]
    media.extract_frames(lib, library.get_entry(library.load_index(lib), entry_id))
    (lib / "media" / f"{entry_id}.gif").unlink()

    report = media.rebuild(lib, prune=True)

    assert report["pruned"] == [entry_id]
    assert entry_id not in library.load_index(lib)["entries"]
    assert not (lib / ".frames" / entry_id).exists()


def test_rebuild_dry_run_changes_nothing(lib, make_png):
    entry_id = media.ingest(lib, [make_png()])["added"][0]["id"]
    (lib / "media" / f"{entry_id}.png").unlink()
    shutil.copy2(make_png(), lib / "media" / "stray.png")
    before = (lib / "index.json").read_text(encoding="utf-8")

    report = media.rebuild(lib, prune=True, dry_run=True)

    assert len(report["added"]) == 1 and report["missing"] == [entry_id]
    assert (lib / "index.json").read_text(encoding="utf-8") == before


def test_rebuild_skips_duplicates_and_non_images(lib, make_png):
    original = make_png()
    entry_id = media.ingest(lib, [original])["added"][0]["id"]
    shutil.copy2(original, lib / "media" / "copy.png")
    (lib / "media" / "notes.txt").write_text("hi", encoding="utf-8")
    (lib / "media" / ".DS_Store").write_bytes(b"\x00")

    report = media.rebuild(lib)

    reasons = {s["path"].replace("\\", "/").rsplit("/", 1)[-1]: s["reason"] for s in report["skipped"]}
    assert reasons == {"copy.png": f"duplicate of {entry_id}", "notes.txt": "unsupported type .txt"}
    assert report["added"] == []


def test_rebuild_without_media_folder_reports_missing_and_recreates_it(lib, make_png):
    entry_id = media.ingest(lib, [make_png()])["added"][0]["id"]
    shutil.rmtree(lib / "media")

    assert media.rebuild(lib, dry_run=True)["missing"] == [entry_id]
    assert not (lib / "media").exists()

    report = media.rebuild(lib)

    assert report["missing"] == [entry_id]
    assert (lib / "media").is_dir()
