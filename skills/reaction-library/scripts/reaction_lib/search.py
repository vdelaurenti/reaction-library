"""Find candidate reactions for a conversational moment.

Search narrows the candidates; the model makes the final pick. Scoring lives in
one swappable function (a Scorer) so alternative strategies can be compared
without touching filtering, ordering, or output.

Words are compared by stem, so "dancing" matches "dance". The default scorer
also expands the query with synonyms.json and weights each word by how rare it
is in the library (IDF), so "printer" counts for more than "good".
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Callable, Iterable
from functools import cache
from pathlib import Path

from .library import SKILL_DIR, load_index, with_path

Scorer = Callable[[list[str], dict], float]

SEARCHABLE = ("tagged", "reviewed")
STOPWORDS = frozenset(
    "a am an and are as at be been but by can could did do does for from has have he her him his "
    "i i'm if in is it it's its me my need needs of on or our she should so some that the their them "
    "then they this to us want wants was we were when will with would you your".split()
)
FIELD_WEIGHTS = {"use_when": 3, "tags": 2, "text": 2, "humor_mechanisms": 2, "emotions": 2, "description": 1}
SUFFIXES = ("ments", "ment", "ness", "ions", "ion", "ings", "ing", "ies", "ied", "es", "ed", "ly", "s")
SYNONYM_WEIGHT = 0.5


@cache
def _synonyms_file() -> dict:
    return json.loads((SKILL_DIR / "synonyms.json").read_text(encoding="utf-8"))


@cache
def _phrase_pattern() -> tuple[re.Pattern[str], dict[str, str]] | None:
    phrases = {" ".join(p.lower().split()): word for p, word in _synonyms_file().get("phrases", {}).items()}
    if not phrases:
        return None
    alternatives = sorted((r"\s+".join(map(re.escape, p.split())) for p in phrases), key=len, reverse=True)
    return re.compile(r"\b(?:" + "|".join(alternatives) + r")\b"), phrases


def join_phrases(text: str) -> str:
    """Rewrite each known phrase ("burned out") to its single word ("burnout")."""
    text = text.lower()
    compiled = _phrase_pattern()
    if compiled is None:
        return text
    pattern, phrases = compiled
    return pattern.sub(lambda m: phrases[" ".join(m.group(0).split())], text)


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9']+", join_phrases(text)) if t not in STOPWORDS]


def stem(token: str) -> str:
    """A deliberately crude stemmer. It only has to map word forms consistently, not produce real words."""
    t = token.replace("'", "")
    for suffix in SUFFIXES:
        if t.endswith(suffix) and len(t) - len(suffix) >= 3:
            t = t[: -len(suffix)] + ("i" if suffix in ("ies", "ied") else "")
            break
    if len(t) > 3 and t.endswith("e"):
        t = t[:-1]
    if len(t) > 3 and t.endswith("y"):
        t = t[:-1] + "i"
    if len(t) > 3 and t[-1] == t[-2] and t[-1] not in "aeiou":
        t = t[:-1]
    return t


def _stems(text: str) -> list[str]:
    return [stem(t) for t in tokenize(text)]


def _field_stems(value: object) -> set[str]:
    if not value:
        return set()
    if isinstance(value, list):
        value = " ".join(value)
    return set(_stems(str(value)))


@cache
def synonym_map() -> dict[str, frozenset[str]]:
    groups = _synonyms_file()["groups"]
    mapping: dict[str, set[str]] = {}
    for group in groups:
        stems = {s for word in group for s in _stems(word)}
        for s in stems:
            mapping.setdefault(s, set()).update(stems - {s})
    return {s: frozenset(others) for s, others in mapping.items()}


def expand_query(tokens: Iterable[str]) -> dict[str, float]:
    """Query stems at weight 1, plus their synonyms at SYNONYM_WEIGHT."""
    weights = {stem(t): 1.0 for t in tokens}
    synonyms = synonym_map()
    for s in list(weights):
        for other in synonyms.get(s, ()):
            weights.setdefault(other, SYNONYM_WEIGHT)
    return weights


def field_weight_score(query_tokens: list[str], entry: dict) -> float:
    """Each query word found in a field adds that field's weight (once per field). No synonyms or IDF."""
    query = {stem(t) for t in query_tokens}
    return sum(weight * len(query & _field_stems(entry.get(field))) for field, weight in FIELD_WEIGHTS.items())


def make_idf_scorer(entries: Iterable[dict]) -> Scorer:
    """Field-weighted score with synonym expansion, each word scaled by 1 + ln(N / entries containing it)."""
    entries = list(entries)
    df = Counter(s for e in entries for s in set().union(*(_field_stems(e.get(f)) for f in FIELD_WEIGHTS)))
    idf = {s: 1 + math.log(len(entries) / n) for s, n in df.items()}

    def score(query_tokens: list[str], entry: dict) -> float:
        query = expand_query(query_tokens)
        total = 0.0
        for field, weight in FIELD_WEIGHTS.items():
            for s in query.keys() & _field_stems(entry.get(field)):
                total += weight * query[s] * idf.get(s, 1.0)
        return round(total, 3)

    return score


def _matches_filters(entry: dict, humor: str | None, emotion: str | None, kind: str | None) -> bool:
    return (
        entry["status"] in SEARCHABLE
        and (humor is None or humor in entry.get("humor_mechanisms", []))
        and (emotion is None or emotion in entry.get("emotions", []))
        and (kind is None or entry["kind"] == kind)
    )


def search_page(
    root: Path,
    query: str,
    humor: str | None = None,
    emotion: str | None = None,
    kind: str | None = None,
    limit: int = 5,
    exclude: Iterable[str] = (),
    scorer: Scorer | None = None,
) -> dict:
    """The top `limit` results plus how many entries matched in total."""
    tokens = sorted(set(tokenize(query)))
    entries = [e for e in load_index(root)["entries"].values() if e["status"] in SEARCHABLE]
    scorer = scorer or make_idf_scorer(entries)
    skip = set(exclude)
    scored = []
    for entry in entries:
        if entry["id"] in skip or not _matches_filters(entry, humor, emotion, kind):
            continue
        score = scorer(tokens, entry)
        if tokens and score <= 0:
            continue
        scored.append((score, entry))

    # Two stable sorts: newest first, then score desc with reviewed ahead of tagged.
    scored.sort(key=lambda pair: pair[1]["added_at"], reverse=True)
    scored.sort(key=lambda pair: (-pair[0], pair[1]["status"] != "reviewed"))
    return {
        "total_matches": len(scored),
        "results": [{**with_path(root, entry), "score": score} for score, entry in scored[:limit]],
    }


def search(root: Path, query: str, **kwargs) -> list[dict]:
    return search_page(root, query, **kwargs)["results"]


def _clean(value: str) -> str:
    return " ".join(value.replace("|", "/").split())


def catalog_lines(root: Path, humor: str | None = None, emotion: str | None = None, kind: str | None = None) -> list[str]:
    entries = sorted(load_index(root)["entries"].values(), key=lambda e: e["id"])
    return [
        " | ".join([
            e["id"],
            e["kind"],
            e["file"],
            _clean(e["description"]),
            ",".join(e["humor_mechanisms"]),
            ",".join(e["emotions"]),
            "; ".join(_clean(u) for u in e["use_when"]),
        ])
        for e in entries
        if _matches_filters(e, humor, emotion, kind)
    ]
