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
4. Run `tag <id> <workdir>/tag.json`. If it's rejected, fix exactly the problems listed and run it again.
5. After the batch, show the user a short table (id, description, use_when) and ask whether the tags look right. If they approve, run `review <id> [<id> ...]`. If they correct one, write a new payload and `tag` it again.

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

1. Run `search "<the moment in a few words>"`. Add `--emotion <term>`, `--humor <term>`, or `--kind animated|static` when the user's intent is clear.
2. Search matches words literally. If results are thin, try two or three phrasings: the situation, the feeling, words likely to be in a caption.
3. For a small library (roughly under 150 tagged entries) you can run `catalog` instead and choose from the whole list.
4. Read each candidate's `use_when` and `avoid_when`, then pick the best one. If nothing really fits, say so; don't force a weak match.
5. Return the result:
   - In chat: give the `path` and a one-line reason it fits.
   - For another tool or channel: hand over the absolute `path`, plus the `text` if useful.

`get <id>` shows a single entry.

## Maintenance

- `retag <id ...>`, `retag --status <untagged|tagged|reviewed>`, or `retag --all` clears tags so the next tagging pass redoes them.
- `rebuild` adds entries for files dropped straight into `media/` and reports entries whose files are gone. `rebuild --prune` removes those missing entries.
- `init` creates an empty library. `ingest` does this automatically, so it's rarely needed.
- `doctor` checks uv, Python, dependencies, the library location, and whether the index matches the files.
