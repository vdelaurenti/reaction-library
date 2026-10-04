---
name: reaction-library
description: Tag and retrieve the user's personal library of reaction GIFs and memes. Use when the user wants to add GIFs, memes, or reaction images to their library, tag or re-tag them, or when a moment calls for a reaction ("got a gif for that?", "react to this", "find me a meme for..."). Returns file paths and metadata; it never posts media anywhere.
---

# reaction-library

A local library of reaction GIFs and memes, each tagged with a short comedic analysis so the right one can be found for a moment in conversation.

## Running commands

Run every command through `uv`, using this skill's own folder (the folder containing this SKILL.md) as `<skill-dir>`:

```
uv run "<skill-dir>/scripts/reaction_library.py" <command> [args]
```

- If `uv` itself is not found, stop and tell the user to install it, then try again. Don't fall back to plain `python`: the dependencies won't be there. Install commands:
  - macOS: `brew install uv`
  - Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows: `winget install --id=astral-sh.uv -e`
- The library lives at `~/.reaction-library/`, or wherever the `REACTION_LIBRARY` environment variable points.
- Commands print JSON, except `catalog` and `doctor`, which print text.
- Never edit `index.json` by hand. Every change goes through a command.
- If a command fails unexpectedly, run `doctor` and tell the user what it reports.

## Adding media

`ingest <files or folders>` copies `.gif .png .jpg .jpeg .webp` files into the library. Folders are scanned recursively. Add `--move` only if the user asks to move the files. The output lists what was `added`, what was a duplicate, and what was skipped and why. Tell the user about any duplicates or skipped files.

## Tagging

When the user asks to tag new media (or right after an ingest, if they want):

1. Run `list --status untagged`.
2. For each entry, run `frames <id>` and look at **every** frame path it returns. The punchline is often in the last frame.
3. Write the analysis as JSON (rules below) to `<workdir>/tag.json`, where `workdir` comes from the `frames` output. Use your file-writing tool, not shell echo.
4. Run `tag <id> <workdir>/tag.json`. If it's rejected, fix exactly the problems listed and run it again. Once it's accepted, the workdir and its frames are deleted.
5. After the batch, show the user a short table (id, description, use_when) and ask whether the tags look right. If they approve, run `review <id> [<id> ...]`. If they correct one, write a new payload and `tag` it again; run `frames <id>` first if you need a workdir or another look.

### Writing the analysis

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

Example:

```json
{
  "description": "A man in an office calmly closes his laptop and stares into the distance.",
  "humor_mechanisms": ["deadpan", "understatement"],
  "emotions": ["exasperation", "despair"],
  "use_when": ["a deploy fails on friday afternoon", "someone schedules a meeting that could have been an email"],
  "avoid_when": ["someone shares genuinely bad news"],
  "tags": ["office", "laptop", "done"],
  "text": null
}
```

## Finding a reaction

Start with the brief catalog; fall back to search when the library is too big for it.

1. Run `catalog --brief` once per conversation. Each line is `file | description | emotions | use_when`, and the header gives the library folder, so a path is `<library>/media/<file>` and the id is the file name without its extension. Choose by meaning; you don't need matching words. Keep the list in mind for follow-ups ("another", "something more upbeat", "three Will Ferrell ones") instead of running more commands.
2. If it prints `too many entries` instead, the library is past the brief-catalog limit (300 by default, or `REACTION_CATALOG_MAX`). Either narrow it with `--emotion`, `--humor` or `--kind` when the request clearly fits one, or use search:
   - `search "<the moment in a few words>"` returns the top 15 in a compact format, plus `total_matches`. It matches word forms ("dancing" finds "dance"), expands common words and merges known phrases ("burned out") using `<skill-dir>/synonyms.json`, and weights rare words higher. If a two-word phrase keeps matching the wrong entries, add it to `phrases` there. If results are thin, try two or three phrasings: the situation, the feeling, words likely to be in a caption.
   - For a mood rather than a moment ("I'm chilling, send me something"), search with an empty query and an emotion filter: `search "" --emotion contentment --kind animated`.
   - For "another", rerun the search with `--exclude <id>,<id>` listing everything already sent in this conversation.
   - `--format full` returns every stored field, which is rarely needed.
3. Before sending your pick, run `get <id>` and check its `avoid_when`; the brief catalog leaves that field out. If it warns against this moment, pick again. Search results already include `avoid_when`.
4. If nothing really fits, say so; don't force a weak match.
5. Return the result:
   - In chat: give the `path` and a one-line reason it fits.
   - For another tool or channel: hand over the absolute `path`, plus the `text` if useful.

`catalog` without `--brief` prints every entry with kind, file, humor and `use_when` in full, for maintenance rather than picking.

## Maintenance

- `retag <id ...>`, `retag --status <untagged|tagged|reviewed>`, or `retag --all` clears tags so the next tagging pass redoes them.
- `rebuild` adds entries for files dropped straight into `media/` and reports entries whose files are gone. `rebuild --prune` removes those missing entries.
- `clean-frames` deletes leftover frames workdirs for entries that are already tagged or gone. `clean-frames --all` also clears untagged ones. `frames` recreates them on demand.
- `init` creates an empty library. `ingest` does this automatically, so it's rarely needed.
- `doctor` checks uv, Python, dependencies, the library location, whether the index matches the files, and whether stale frames are piling up.
