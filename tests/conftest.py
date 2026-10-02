import copy
import itertools

import pytest
from PIL import Image

VALID_PAYLOAD = {
    "description": "A man slowly closes his laptop and stares into the distance.",
    "humor_mechanisms": ["deadpan"],
    "emotions": ["exasperation"],
    "use_when": ["a deploy fails on friday afternoon"],
    "avoid_when": ["someone is genuinely upset"],
    "tags": ["laptop", "office"],
    "text": None,
}


@pytest.fixture
def lib(tmp_path, monkeypatch):
    """Path for a library that does not exist yet; REACTION_LIBRARY points at it."""
    root = tmp_path / "library"
    monkeypatch.setenv("REACTION_LIBRARY", str(root))
    return root


@pytest.fixture
def incoming(tmp_path):
    folder = tmp_path / "incoming"
    folder.mkdir()
    return folder


_seeds = itertools.count(1)


@pytest.fixture
def make_gif(incoming):
    """Write a small animated GIF with distinct frames. Each call yields unique bytes."""

    def _make(name=None, frames=3):
        seed = next(_seeds)
        path = incoming / (name or f"gif{seed}.gif")
        images = [Image.new("RGB", (8, 8), ((i * 25) % 256, (seed * 37) % 256, 128)) for i in range(frames)]
        images[0].save(path, save_all=True, append_images=images[1:], duration=100, loop=0)
        return path

    return _make


@pytest.fixture
def make_png(incoming):
    """Write a small static PNG. Each call yields unique bytes."""

    def _make(name=None):
        seed = next(_seeds)
        path = incoming / (name or f"png{seed}.png")
        Image.new("RGB", (8, 8), ((seed * 37) % 256, (seed * 11) % 256, 200)).save(path)
        return path

    return _make


@pytest.fixture
def payload():
    return copy.deepcopy(VALID_PAYLOAD)
