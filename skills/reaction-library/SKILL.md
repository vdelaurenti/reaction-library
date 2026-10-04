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

## First run

A new user starts with an empty library. These are normal states, not failures; don't run `doctor` for them:

- `No library at ...`: nothing has been added yet. Tell the user the library starts empty and ask for a folder or files of GIFs and memes to add (for example ones saved from Slack, Giphy, or their downloads), then `ingest` them.
- `(no tagged entries; N untagged waiting to be tagged)` from `catalog`, or an `untagged` count in `search` output: media was added but not tagged yet, so nothing can be found. Offer to tag it instead of saying nothing fits.

## Adding media

`ingest <files or folders>` copies `.gif .png .jpg .jpeg .webp` files into the library. Folders are scanned recursively. Add `--move` only if the user asks to move the files. The output lists what was `added`, what was a duplicate, and what was skipped and why. Tell the user about any duplicates or skipped files.

## Tagging

When the user asks to tag new media (or right after an ingest, if they want), you coordinate and workers do the looking. Tagging is the expensive part (images plus a JSON payload per GIF), and nothing about one GIF is needed once its tag is saved, so keep it out of this conversation.

1. Run `list --status untagged` and split the ids into batches of 10.
2. **If you can start subagents** (for example Claude Code's Agent/Task tool), start one worker per batch, up to 3 at a time, each with a short brief: "Follow `<skill-dir>/tagging-worker.md` to tag these ids: …". The library is locked during writes, so parallel workers are safe. Start the next batch as one finishes.
   **If you can't,** follow `<skill-dir>/tagging-worker.md` yourself, one batch per turn, and tell the user how many are left after each.
3. Each worker reports one line per GIF: `id | description | use_when; ...`, with `| FLAG: …` when it wasn't sure, or `id | FAILED: …`. Keep these lines; don't re-fetch anything.
4. When all batches are done, give the user a short summary, not a table: how many were tagged, then only the flagged and failed ones with their reasons. Workers have already checked their own tags against a self-review checklist, so the tags are usable as they are.
5. Offer optional refinement: they can ask to see the tags (print the lines you kept as a table), or play the quiz (show GIFs blind, compare their guess with `use_when`, merge their wording in). **Never run `review` unless the user approved those specific tags**: `reviewed` means a person checked it, and search and the quiz rely on that.

To fix one tag after a correction: `frames <id>` if you need another look, write the payload following `tagging-worker.md`, then `tag <id> <file>`. It prints `{"id", "status"}`; use `get <id>` to see what's stored.

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

**Reacting without being asked?** If your persona sends reactions on its own initiative, read `<skill-dir>/persona.md` first: when to react and when not to, how often, and a taste profile to fill in.

## Maintenance

- `retag <id ...>`, `retag --status <untagged|tagged|reviewed>`, or `retag --all` clears tags so the next tagging pass redoes them.
- `rebuild` adds entries for files dropped straight into `media/` and reports entries whose files are gone. `rebuild --prune` removes those missing entries.
- `clean-frames` deletes leftover frames workdirs for entries that are already tagged or gone. `clean-frames --all` also clears untagged ones. `frames` recreates them on demand.
- `init` creates an empty library. `ingest` does this automatically, so it's rarely needed.
- `doctor` checks uv, Python, dependencies, the library location, whether the index matches the files, and whether stale frames are piling up.
