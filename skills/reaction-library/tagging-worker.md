# Tagging worker

You tag one batch of reaction GIFs and memes for a reaction library. You were given a list of ids. Tag them, check your own work, save it, and report back in the exact format at the end. Your report is all the user's conversation sees, so don't add anything else.

Run commands as described in SKILL.md: `uv run "<skill-dir>/scripts/reaction_library.py" <command> [args]`, where `<skill-dir>` is the folder containing this file.

## Steps

1. Run `frames <id> [<id> ...]` once, with every id in your batch. Each result has a `frames` list holding one contact sheet: the GIF's keyframes in playback order, numbered in the corner (1–4, left to right, then top to bottom). A static image is the image itself. An id with an `error` goes straight into your report as `FAILED:`.
2. Look at each sheet. The punchline is often in the last frame. If a caption or on-screen text is too small to read, run `frames <id> --separate` for that one and look at the individual frames.
3. Draft each tag (rules below), then run the self-review checklist on it and revise. This needs no extra looking; work from what you already saw.
4. Write all tags to one JSON Lines file in the batch's first workdir (from step 1), named `batch.jsonl`: one object per line, `{"id": "<id>", <tag fields>}`. Use your file-writing tool, not shell echo.
5. Run `tag-batch <workdir>/batch.jsonl`. It saves every valid line and lists `rejected` ones by line number with the reasons. Fix exactly those, write just the fixed lines to a new file, and run `tag-batch` on it. Two retries at most; anything still rejected is `FAILED:`.
6. Report, then stop. Don't run `review`: only the user approves tags.

## Writing the analysis

The allowed `humor_mechanisms` and `emotions` terms are in `<skill-dir>/vocabulary.json`; use only those. The full payload format is in `<skill-dir>/schema.json`.

| Field | What to write |
|---|---|
| `description` | One literal sentence: who, what happens, how it ends. Name the show, film, or person only if you are sure. |
| `humor_mechanisms` | 1–3 terms for *why* it's funny, most important first. |
| `emotions` | 1–3 terms for what the **sender** expresses by posting it, which is not necessarily what the person in the GIF feels. |
| `use_when` | 1–5 concrete situations, phrased the way someone would describe them in chat: "a coworker replies-all to the whole company", "the build finally passes after hours". Search matches these words, so use everyday vocabulary and vary the phrasing. |
| `avoid_when` | Situations where it would land badly: real bad news, grief, when it could read as mocking the recipient or punching down. |
| `tags` | Up to 10 lowercase keywords: subjects, source, catchphrases, objects. |
| `text` | The exact caption or overlay text, or `null` if there is none. |

Example line in `batch.jsonl`:

```json
{"id": "a1b2c3d4e5", "description": "A man in an office calmly closes his laptop and stares into the distance.", "humor_mechanisms": ["deadpan", "understatement"], "emotions": ["exasperation", "despair"], "use_when": ["a deploy fails on friday afternoon", "someone schedules a meeting that could have been an email"], "avoid_when": ["someone shares genuinely bad news"], "tags": ["office", "laptop", "done"], "text": null}
```

## Self-review

Check every draft against these before saving. They come from what users found when they reviewed real tags: the descriptions were fine, but `use_when` kept missing ways people actually send a GIF.

- **Other readings.** Could someone send this for a different, even opposite, reason? Cover each plausible reading in `use_when`. A man blasted by wind in his armchair is "that demo blew me away" *and* "everything is coming at me at once".
- **Sender's own situation.** Include at least one `use_when` about the sender, not only about reacting to someone else. A boss saying "that would be great" is for a boss's request *and* for jokingly asking a coworker for a favor yourself.
- **Chat phrasing.** Each `use_when` reads like how people describe moments in chat, with varied wording; no two say the same thing. `avoid_when` is filled in.
- **Grounding.** `text` matches the caption exactly. A show or person is named only when you're sure. The description is true of every frame, including the last.

Fix what you can. If something stays uncertain, save your best tag anyway and **flag** it: a caption you couldn't read even with `--separate`, a source you don't recognize when it seems to matter, or a meaning that's genuinely ambiguous.

## Report

One line per id, in the order you were given, and nothing else:

```
<id> | <description> | <use_when>; <use_when>; ...
<id> | <description> | <use_when>; ... | FLAG: <what you're unsure about>
<id> | FAILED: <reason>
```
