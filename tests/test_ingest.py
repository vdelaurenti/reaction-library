from pathlib import Path

from PIL import Image

from reaction_lib import library, media


def _entry(lib, entry_id):
    return library.get_entry(library.load_index(lib), entry_id)


def test_ingest_copies_animated_and_static(lib, make_gif, make_png):
    gif = make_gif("dance.gif")
    png = make_png("meme.png")

    report = media.ingest(lib, [gif, png])

    assert [a["kind"] for a in report["added"]] == ["animated", "static"]
    assert report["duplicates"] == [] and report["skipped"] == []
    entry = _entry(lib, report["added"][0]["id"])
    assert entry["status"] == "untagged"
    assert entry["original_name"] == "dance.gif"
    assert len(entry["id"]) == 10 and entry["sha256"].startswith(entry["id"])
    assert entry["file"] == f"media/{entry['id']}.gif"
    assert library.entry_path(lib, entry).read_bytes() == gif.read_bytes()
    assert gif.exists() and png.exists()


def test_ingest_creates_library_on_first_use(lib, make_png):
    assert not lib.exists()
    media.ingest(lib, [make_png()])
    assert (lib / "index.json").exists()


def test_ingest_move_deletes_source(lib, make_png):
    png = make_png()
    report = media.ingest(lib, [png], move=True)
    assert len(report["added"]) == 1
    assert not png.exists()


def test_ingest_dedupes_and_never_deletes_duplicate_source(lib, make_gif):
    gif = make_gif("a.gif")
    first = media.ingest(lib, [gif])["added"][0]["id"]
    copy = gif.with_name("again.gif")
    copy.write_bytes(gif.read_bytes())

    report = media.ingest(lib, [copy], move=True)

    assert report["added"] == []
    assert report["duplicates"] == [{"path": str(copy), "id": first}]
    assert copy.exists()


def test_ingest_skips_unsupported_corrupt_and_missing(lib, incoming, make_png):
    txt = incoming / "notes.txt"
    txt.write_text("hi", encoding="utf-8")
    bad = incoming / "broken.gif"
    bad.write_bytes(b"GIF89a garbage")
    good = make_png("ok.png")

    report = media.ingest(lib, [txt, bad, good, incoming / "missing.png"])

    reasons = {Path(s["path"]).name: s["reason"] for s in report["skipped"]}
    assert "unsupported" in reasons["notes.txt"]
    assert reasons["broken.gif"].startswith("Not a readable image")
    assert reasons["missing.png"] == "not found"
    assert [Path(a["path"]).name for a in report["added"]] == ["ok.png"]


def test_ingest_folder_is_recursive_and_ignores_hidden_files(lib, incoming, make_gif, make_png):
    (incoming / "nested").mkdir()
    make_gif("nested/deep.gif")
    make_png("top.png")
    (incoming / ".DS_Store").write_bytes(b"\x00\x01")

    report = media.ingest(lib, [incoming])

    assert sorted(Path(a["path"]).name for a in report["added"]) == ["deep.gif", "top.png"]
    assert report["skipped"] == []


def test_ingest_uppercase_and_mislabelled_extensions(lib, incoming, make_png):
    shout = make_png("SHOUT.PNG")
    liar = incoming / "actually_png.gif"
    liar.write_bytes(make_png("source.png").read_bytes())

    report = media.ingest(lib, [shout, liar])

    added = {Path(a["path"]).name: a for a in report["added"]}
    assert added["SHOUT.PNG"]["kind"] == "static"
    assert _entry(lib, added["SHOUT.PNG"]["id"])["file"].endswith(".png")
    assert added["actually_png.gif"]["kind"] == "static"


def test_animated_webp_is_animated(incoming):
    frames = [Image.new("RGB", (8, 8), (i * 60, 0, 0)) for i in range(3)]
    path = incoming / "anim.webp"
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=100)
    assert media.detect_kind(path) == "animated"


def test_assign_id_extends_on_collision():
    sha = "abcdef0123456789" * 4
    assert media.assign_id(sha, {}) == "abcdef0123"
    assert media.assign_id(sha, {"abcdef0123": {}}) == "abcdef012345"
