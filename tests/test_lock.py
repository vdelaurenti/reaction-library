import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from reaction_lib import library, media
from reaction_lib.library import LibraryError

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "reaction-library" / "scripts" / "reaction_library.py"


def test_lock_is_created_and_released(lib):
    library.init_library(lib)
    with library.index_lock(lib):
        assert (lib / "index.lock").exists()
    assert not (lib / "index.lock").exists()


def test_lock_is_released_on_error(lib):
    library.init_library(lib)
    with pytest.raises(RuntimeError):
        with library.index_lock(lib):
            raise RuntimeError("boom")
    assert not (lib / "index.lock").exists()


def test_second_writer_waits_for_the_first(lib):
    library.init_library(lib)
    released = threading.Event()

    def hold():
        with library.index_lock(lib):
            time.sleep(0.3)
        released.set()

    holder = threading.Thread(target=hold)
    holder.start()
    time.sleep(0.05)
    with library.index_lock(lib):
        assert released.is_set()
    holder.join()


def test_lock_times_out_with_clear_error(lib, monkeypatch):
    library.init_library(lib)
    (lib / "index.lock").write_text("someone else", encoding="utf-8")
    monkeypatch.setattr(library, "LOCK_TIMEOUT", 0.2)

    with pytest.raises(LibraryError, match="index.lock"):
        with library.index_lock(lib):
            pass


def test_stale_lock_is_removed(lib):
    library.init_library(lib)
    lock = lib / "index.lock"
    lock.write_text("crashed", encoding="utf-8")
    old = time.time() - library.LOCK_STALE - 10
    os.utime(lock, (old, old))

    with library.index_lock(lib):
        pass
    assert not lock.exists()


def test_concurrent_tag_processes_lose_nothing(lib, make_png, tmp_path, payload):
    ids = [media.ingest(lib, [make_png()])["added"][0]["id"] for _ in range(8)]
    payload_file = tmp_path / "p.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")
    env = {**os.environ, "REACTION_LIBRARY": str(lib)}

    procs = [subprocess.Popen([sys.executable, str(SCRIPT), "tag", i, str(payload_file)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env) for i in ids]
    errors = [p.communicate()[1] for p in procs]

    assert all(p.returncode == 0 for p in procs), errors
    entries = library.load_index(lib)["entries"]
    assert all(entries[i]["status"] == "tagged" for i in ids)
