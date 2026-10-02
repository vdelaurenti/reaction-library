import pytest

from reaction_lib import library, media, search, tagging


@pytest.fixture
def add_tagged(lib, make_png, make_gif):
    def _add(status="tagged", kind="static", **fields):
        path = make_png() if kind == "static" else make_gif()
        entry_id = media.ingest(lib, [path])["added"][0]["id"]
        payload = {
            "description": "placeholder scene",
            "humor_mechanisms": ["deadpan"],
            "emotions": ["approval"],
            "use_when": ["generic moment"],
            **fields,
        }
        tagging.tag(lib, entry_id, payload)
        if status == "reviewed":
            tagging.review(lib, [entry_id])
        return entry_id

    return _add


def _set_added_at(lib, entry_id, value):
    index = library.load_index(lib)
    index["entries"][entry_id]["added_at"] = value
    library.save_index(lib, index)


def test_tokenize_drops_stopwords_and_punctuation():
    assert search.tokenize("This is FINE, really!") == ["fine", "really"]
    assert search.tokenize("don't panic") == ["don't", "panic"]


def test_field_weight_score_sums_weighted_matches():
    entry = {"use_when": ["the deploy failed"], "tags": ["deploy"], "description": "a deploy explodes"}
    assert search.field_weight_score(["deploy"], entry) == 6
    assert search.field_weight_score(["nothing"], entry) == 0


def test_use_when_outranks_description(lib, add_tagged):
    in_description = add_tagged(description="a printer catches fire")
    in_use_when = add_tagged(use_when=["the printer jams again"])

    results = search.search(lib, "printer")

    assert [r["id"] for r in results] == [in_use_when, in_description]
    assert results[0]["score"] == 3 and results[1]["score"] == 1
    assert results[0]["path"] == str(lib / "media" / f"{in_use_when}.png")


def test_untagged_and_zero_score_entries_excluded(lib, make_png, add_tagged):
    media.ingest(lib, [make_png()])
    add_tagged(use_when=["unrelated"])
    assert search.search(lib, "printer") == []


def test_filters(lib, add_tagged):
    smug = add_tagged(emotions=["smugness"], humor_mechanisms=["irony"], use_when=["told you so"])
    add_tagged(emotions=["panic"], use_when=["told you so"])
    animated = add_tagged(kind="animated", emotions=["smugness"], use_when=["told you so"])

    assert {r["id"] for r in search.search(lib, "told", emotion="smugness")} == {smug, animated}
    assert [r["id"] for r in search.search(lib, "told", humor="irony")] == [smug]
    assert [r["id"] for r in search.search(lib, "told", emotion="smugness", kind="animated")] == [animated]


def test_ties_prefer_reviewed_then_newest(lib, add_tagged):
    old = add_tagged(use_when=["monday morning"])
    new = add_tagged(use_when=["monday morning"])
    reviewed = add_tagged(status="reviewed", use_when=["monday morning"])
    _set_added_at(lib, old, "2026-01-01T00:00:00Z")
    _set_added_at(lib, new, "2026-06-01T00:00:00Z")
    _set_added_at(lib, reviewed, "2025-01-01T00:00:00Z")

    assert [r["id"] for r in search.search(lib, "monday")] == [reviewed, new, old]


def test_stopword_only_query_returns_filtered_entries(lib, add_tagged):
    ids = {add_tagged(), add_tagged()}
    results = search.search(lib, "this is it")
    assert {r["id"] for r in results} == ids
    assert all(r["score"] == 0 for r in results)


def test_limit(lib, add_tagged):
    for _ in range(4):
        add_tagged(use_when=["coffee time"])
    assert len(search.search(lib, "coffee", limit=2)) == 2


def test_custom_scorer_is_used(lib, add_tagged):
    add_tagged()
    target = add_tagged()

    results = search.search(lib, "anything", scorer=lambda tokens, entry: 1.0 if entry["id"] == target else 0.0)

    assert [r["id"] for r in results] == [target]


def test_catalog_lines(lib, make_png, add_tagged):
    media.ingest(lib, [make_png()])
    entry_id = add_tagged(
        description="Cat | knocks\nglass over",
        humor_mechanisms=["slapstick", "chaos"],
        emotions=["joy"],
        use_when=["chaos at work", "friday"],
    )

    assert search.catalog_lines(lib) == [
        f"{entry_id} | Cat / knocks glass over | slapstick,chaos | joy | chaos at work; friday"
    ]


def test_catalog_empty(lib):
    library.init_library(lib)
    assert search.catalog_lines(lib) == []
