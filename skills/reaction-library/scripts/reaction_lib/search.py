"""Find candidate reactions for a conversational moment.

Search narrows the candidates; the model makes the final pick. Scoring lives in
one swappable function (a Scorer) so alternative strategies can be compared
without touching filtering, ordering, or output.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from .library import load_index, with_path

Scorer = Callable[[list[str], dict], float]

SEARCHABLE = ("tagged", "reviewed")
STOPWORDS = frozenset(
    "a an and are as at be but by for from has have i i'm in is it it's its me my of on or "
    "so that the their them they this to was we were when with you your".split()
)
FIELD_WEIGHTS = {"use_when": 3, "tags": 2, "text": 2, "humor_mechanisms": 2, "emotions": 2, "description": 1}


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9']+", text.lower()) if t not in STOPWORDS]


def _field_tokens(value: object) -> set[str]:
    if not value:
        return set()
    if isinstance(value, list):
        value = " ".join(value)
    return set(tokenize(str(value)))


def field_weight_score(query_tokens: list[str], entry: dict) -> float:
    """Each query word found in a field adds that field's weight (once per field)."""
    score = 0.0
    for field, weight in FIELD_WEIGHTS.items():
        present = _field_tokens(entry.get(field))
        score += weight * sum(1 for token in query_tokens if token in present)
    return score


def search(
    root: Path,
    query: str,
    humor: str | None = None,
    emotion: str | None = None,
    kind: str | None = None,
    limit: int = 5,
    scorer: Scorer = field_weight_score,
) -> list[dict]:
    tokens = sorted(set(tokenize(query)))
    scored = []
    for entry in load_index(root)["entries"].values():
        if entry["status"] not in SEARCHABLE:
            continue
        if humor and humor not in entry.get("humor_mechanisms", []):
            continue
        if emotion and emotion not in entry.get("emotions", []):
            continue
        if kind and entry["kind"] != kind:
            continue
        score = scorer(tokens, entry)
        if tokens and score <= 0:
            continue
        scored.append((score, entry))

    # Two stable sorts: newest first, then score desc with reviewed ahead of tagged.
    scored.sort(key=lambda pair: pair[1]["added_at"], reverse=True)
    scored.sort(key=lambda pair: (-pair[0], pair[1]["status"] != "reviewed"))
    return [{**with_path(root, entry), "score": score} for score, entry in scored[:limit]]


def _clean(value: str) -> str:
    return " ".join(value.replace("|", "/").split())


def catalog_lines(root: Path) -> list[str]:
    entries = sorted(load_index(root)["entries"].values(), key=lambda e: e["id"])
    return [
        " | ".join([
            e["id"],
            _clean(e["description"]),
            ",".join(e["humor_mechanisms"]),
            ",".join(e["emotions"]),
            "; ".join(_clean(u) for u in e["use_when"]),
        ])
        for e in entries
        if e["status"] in SEARCHABLE
    ]
