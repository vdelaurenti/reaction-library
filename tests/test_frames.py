from pathlib import Path

import pytest

from reaction_lib import library, media
from reaction_lib.library import LibraryError


def _ingest_one(lib, path):
    entry_id = media.ingest(lib, [path])["added"][0]["id"]
    return library.get_entry(library.load_index(lib), entry_id)


def test_keyframe_indices():
    assert media.keyframe_indices(1) == [0]
    assert media.keyframe_indices(3) == [0, 1, 2]
    assert media.keyframe_indices(5) == [0, 1, 3, 4]
    assert media.keyframe_indices(10) == [0, 3, 6, 9]


def test_frames_for_animated(lib, make_gif):
    entry = _ingest_one(lib, make_gif(frames=10))

    result = media.extract_frames(lib, entry)

    assert result["id"] == entry["id"]
    assert Path(result["workdir"]) == lib / ".frames" / entry["id"]
    assert [Path(p).name for p in result["frames"]] == [f"frame-{i}.png" for i in range(4)]
    assert all(Path(p).exists() for p in result["frames"])


def test_frames_rerun_removes_stale_frames(lib, make_gif):
    entry = _ingest_one(lib, make_gif(frames=2))
    workdir = lib / ".frames" / entry["id"]
    workdir.mkdir(parents=True)
    (workdir / "frame-9.png").write_bytes(b"old")

    result = media.extract_frames(lib, entry)

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
