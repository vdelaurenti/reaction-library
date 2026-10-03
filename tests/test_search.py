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
    assert results[0]["score"] == pytest.approx(3 * results[1]["score"])
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


@pytest.mark.parametrize("words", [
    ("dance", "dancing", "dances"),
    ("party", "partying", "parties"),
    ("celebrate", "celebrating", "celebration", "celebrates"),
    ("relax", "relaxing", "relaxed"),
    ("chill", "chilling"),
    ("hype", "hyped"),
    ("excited", "exciting", "excitement"),
    ("happy", "happiness"),
    ("win", "wins", "winning"),
    ("can't", "cant"),
])
def test_stem_conflates_word_forms(words):
    assert len({search.stem(w) for w in words}) == 1


def test_stem_leaves_short_words_alone():
    assert search.stem("yes") == "yes"
    assert search.stem("red") == "red"


def test_search_matches_other_word_forms(lib, add_tagged):
    target = add_tagged(use_when=["happy dance after a win"])
    assert [r["id"] for r in search.search(lib, "dancing")] == [target]
    assert [r["id"] for r in search.search(lib, "winning")] == [target]


def test_synonyms_expand_query_at_lower_weight(lib, add_tagged):
    synonym_only = add_tagged(use_when=["relaxing with coffee"])
    exact = add_tagged(use_when=["just chilling"])

    results = search.search(lib, "chill")

    assert [r["id"] for r in results] == [exact, synonym_only]
    assert results[1]["score"] < results[0]["score"]


def test_synonym_reaches_emotion_terms(lib, add_tagged):
    joyful = add_tagged(emotions=["joy", "excitement"], use_when=["good news"])
    assert [r["id"] for r in search.search(lib, "upbeat")] == [joyful]


def test_rare_words_outweigh_common_ones(lib, add_tagged):
    for _ in range(4):
        add_tagged(use_when=["good morning"])
    rare = add_tagged(use_when=["a printer jams"])
    both = add_tagged(use_when=["good printer"])

    ids = [r["id"] for r in search.search(lib, "good printer")]

    assert ids[:2] == [both, rare]


def test_phrases_are_searched_as_one_word(lib, add_tagged):
    tired = add_tagged(use_when=["exhausted after a long day"])
    add_tagged(use_when=["the server room is burning"])
    add_tagged(use_when=["heading out for lunch"])

    assert [r["id"] for r in search.search(lib, "burned out")] == [tired]


def test_filler_words_do_not_match(lib, add_tagged):
    add_tagged(use_when=["needs some spending money"])
    nap = add_tagged(tags=["nap"])
    actor = add_tagged(description="Will Ferrell yells at a referee")
    add_tagged(text="I will never forget it")

    assert [r["id"] for r in search.search(lib, "need a nap")] == [nap]
    assert [r["id"] for r in search.search(lib, "will ferrell")] == [actor]


def test_exclude_skips_ids(lib, add_tagged):
    first = add_tagged(use_when=["coffee time"])
    second = add_tagged(use_when=["coffee time"])
    assert [r["id"] for r in search.search(lib, "coffee", exclude=[first])] == [second]


def test_search_page_reports_total_matches(lib, add_tagged):
    for _ in range(4):
        add_tagged(use_when=["coffee time"])
    page = search.search_page(lib, "coffee", limit=2)
    assert page["total_matches"] == 4
    assert len(page["results"]) == 2


def test_catalog_lines(lib, make_png, add_tagged):
    media.ingest(lib, [make_png()])
    entry_id = add_tagged(
        description="Cat | knocks\nglass over",
        humor_mechanisms=["slapstick", "chaos"],
        emotions=["joy"],
        use_when=["chaos at work", "friday"],
    )

    assert search.catalog_lines(lib) == [
        f"{entry_id} | static | media/{entry_id}.png | Cat / knocks glass over | slapstick,chaos | joy | chaos at work; friday"
    ]


def test_catalog_filters(lib, add_tagged):
    joyful = add_tagged(kind="animated", emotions=["joy"])
    add_tagged(emotions=["joy"])
    add_tagged(kind="animated", emotions=["panic"])

    lines = search.catalog_lines(lib, emotion="joy", kind="animated")

    assert [line.split(" | ")[0] for line in lines] == [joyful]


def test_catalog_empty(lib):
    library.init_library(lib)
    assert search.catalog_lines(lib) == []
