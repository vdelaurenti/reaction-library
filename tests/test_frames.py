from pathlib import Path

import pytest
from PIL import Image

from reaction_lib import library, media, tagging
from reaction_lib.library import LibraryError


def _ingest_one(lib, path):
    entry_id = media.ingest(lib, [path])["added"][0]["id"]
    return library.get_entry(library.load_index(lib), entry_id)


def test_keyframe_indices():
    assert media.keyframe_indices(1) == [0]
    assert media.keyframe_indices(3) == [0, 1, 2]
    assert media.keyframe_indices(5) == [0, 1, 3, 4]
    assert media.keyframe_indices(10) == [0, 3, 6, 9]


def test_frames_separate_for_animated(lib, make_gif):
    entry = _ingest_one(lib, make_gif(frames=10))

    result = media.extract_frames(lib, entry, separate=True)

    assert result["id"] == entry["id"]
    assert Path(result["workdir"]) == lib / ".frames" / entry["id"]
    assert [Path(p).name for p in result["frames"]] == [f"frame-{i}.png" for i in range(4)]
    assert all(Path(p).exists() for p in result["frames"])


def test_frames_rerun_removes_stale_frames(lib, make_gif):
    entry = _ingest_one(lib, make_gif(frames=2))
    workdir = lib / ".frames" / entry["id"]
    workdir.mkdir(parents=True)
    (workdir / "frame-9.png").write_bytes(b"old")

    result = media.extract_frames(lib, entry, separate=True)

    assert len(result["frames"]) == 2
    assert not (workdir / "frame-9.png").exists()


def test_frames_for_static_returns_media_file(lib, make_png):
    entry = _ingest_one(lib, make_png())

    result = media.extract_frames(lib, entry)

    assert result["frames"] == [str(library.entry_path(lib, entry))]
    assert Path(result["workdir"]).is_dir()


def test_frames_missing_media_points_to_rebuild(lib, make_png):
    entry = _ingest_one(lib, make_png())
    library.entry_path(lib, entry).unlink()

    with pytest.raises(LibraryError, match="rebuild"):
        media.extract_frames(lib, entry)


def _gif(path, frames, size):
    images = [Image.new("RGB", size, (i * 40 % 256, 90, 160)) for i in range(frames)]
    images[0].save(path, save_all=True, append_images=images[1:], duration=100, loop=0)
    return path


@pytest.mark.parametrize("frames,cols,rows", [(10, 2, 2), (4, 2, 2), (3, 3, 1), (2, 2, 1)])
def test_sheet_layout(lib, incoming, frames, cols, rows):
    entry = _ingest_one(lib, _gif(incoming / f"g{frames}.gif", frames, (1000, 500)))

    result = media.extract_frames(lib, entry)

    [sheet] = result["frames"]
    assert Path(sheet).name == "sheet.png"
    tile_w, tile_h = media.SHEET_TILE_WIDTH, media.SHEET_TILE_WIDTH // 2
    with Image.open(sheet) as im:
        assert im.size == (cols * tile_w + (cols - 1) * media.SHEET_GAP, rows * tile_h + (rows - 1) * media.SHEET_GAP)


def test_sheet_never_upscales_small_frames(lib, make_gif):
    entry = _ingest_one(lib, make_gif(frames=4))

    [sheet] = media.extract_frames(lib, entry)["frames"]

    with Image.open(sheet) as im:
        assert im.size == (2 * 8 + media.SHEET_GAP, 2 * 8 + media.SHEET_GAP)


def test_sheet_replaces_separate_frames_and_vice_versa(lib, make_gif):
    entry = _ingest_one(lib, make_gif(frames=4))
    workdir = lib / ".frames" / entry["id"]

    media.extract_frames(lib, entry, separate=True)
    media.extract_frames(lib, entry)
    assert sorted(p.name for p in workdir.iterdir()) == ["sheet.png"]

    media.extract_frames(lib, entry, separate=True)
    assert sorted(p.name for p in workdir.iterdir()) == [f"frame-{i}.png" for i in range(4)]


def test_large_static_is_downscaled_into_a_sheet(lib, incoming):
    path = incoming / "big.png"
    Image.new("RGB", (2000, 1000), (10, 20, 30)).save(path)
    entry = _ingest_one(lib, path)

    [sheet] = media.extract_frames(lib, entry)["frames"]

    assert Path(sheet).name == "sheet.png"
    with Image.open(sheet) as im:
        assert im.size == (media.STATIC_MAX_EDGE, media.STATIC_MAX_EDGE // 2)


def test_extract_many_reports_bad_ids_without_failing_the_rest(lib, make_gif):
    entry = _ingest_one(lib, make_gif())

    results = media.extract_many(lib, [entry["id"], "nope"])

    assert results[0]["id"] == entry["id"] and results[0]["frames"]
    assert results[1] == {"id": "nope", "error": "Unknown id: nope"}


def _set_status(lib, entry_id, status):
    index = library.load_index(lib)
    index["entries"][entry_id]["status"] = status
    library.save_index(lib, index)


def test_successful_tag_removes_frames_workdir(lib, make_gif, payload):
    entry = _ingest_one(lib, make_gif())
    workdir = Path(media.extract_frames(lib, entry)["workdir"])
    (workdir / "tag.json").write_text("{}", encoding="utf-8")

    tagging.tag(lib, entry["id"], payload)

    assert not workdir.exists()


def test_rejected_tag_keeps_frames_workdir(lib, make_gif, payload):
    entry = _ingest_one(lib, make_gif())
    workdir = Path(media.extract_frames(lib, entry)["workdir"])
    del payload["description"]

    with pytest.raises(LibraryError):
        tagging.tag(lib, entry["id"], payload)

    assert workdir.is_dir()


def test_clean_frames_keeps_untagged_and_removes_the_rest(lib, make_gif):
    untagged, tagged, reviewed = (_ingest_one(lib, make_gif()) for _ in range(3))
    for entry in (untagged, tagged, reviewed):
        media.extract_frames(lib, entry)
    _set_status(lib, tagged["id"], "tagged")
    _set_status(lib, reviewed["id"], "reviewed")
    orphan = lib / ".frames" / "gone000000"
    orphan.mkdir()
    (orphan / "frame-0.png").write_bytes(b"x" * 10)

    result = library.clean_frames(lib)

    assert result["removed"] == sorted([tagged["id"], reviewed["id"], "gone000000"])
    assert result["freed_bytes"] > 10
    assert (lib / ".frames" / untagged["id"]).is_dir()
    assert not orphan.exists()


def test_clean_frames_all_removes_untagged_too(lib, make_gif):
    entry = _ingest_one(lib, make_gif())
    media.extract_frames(lib, entry)

    result = library.clean_frames(lib, all_folders=True)

    assert result["removed"] == [entry["id"]]
    assert list((lib / ".frames").iterdir()) == []


def test_clean_frames_without_frames_folder(lib, make_gif):
    _ingest_one(lib, make_gif())
    (lib / ".frames").rmdir()

    assert library.clean_frames(lib) == {"removed": [], "freed_bytes": 0}
