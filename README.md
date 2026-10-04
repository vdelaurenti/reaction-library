# reaction-library

An [Agent Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills) that keeps a personal library of reaction GIFs and memes. Each one gets a short comedic analysis (why it's funny, what it says, when to use it, and when not to), so your AI assistant can find the right reaction for the moment.

It does two things:

- **Tag:** you add files, and the model looks at them and records the analysis.
- **Retrieve:** given a moment in conversation, it finds the best fit and returns the file path. What happens next is up to you or your tools; the skill never posts anything.

## Requirements

- [uv](https://docs.astral.sh/uv/). It provides Python and the dependencies automatically.
  - macOS: `brew install uv`
  - Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows: `winget install --id=astral-sh.uv -e`
- An agent that can run local commands, such as [Claude Code](https://claude.com/claude-code).

## Install

### Claude Code (recommended)

```
/plugin marketplace add vdelaurenti/reaction-library
/plugin install reaction-library@reaction-library
```

### Manual install

Copy the skill folder into your Claude Code skills directory:

- macOS / Linux: `cp -R skills/reaction-library ~/.claude/skills/`
- Windows (PowerShell): `Copy-Item -Recurse skills\reaction-library $HOME\.claude\skills\`

Other agents that read `SKILL.md` folders can use the same `skills/reaction-library/` folder; copy it into that agent's skills directory.

## Usage

Just talk to your assistant:

- "Add the GIFs in ~/Downloads/reactions to my reaction library"
- "Tag my new reactions"
- "Got a gif for when the build finally passes?"

The library is created the first time you add something.

## Where your library lives

By default it lives in `~/.reaction-library/` (`C:\Users\<you>\.reaction-library` on Windows):

```
index.json     the tags
media/         your files, renamed to their ids
.frames/       keyframes for tagging, deleted once a tag is saved (safe to delete)
```

To keep it somewhere else, for example a synced folder, set `REACTION_LIBRARY`:

- macOS / Linux: add `export REACTION_LIBRARY="$HOME/Dropbox/reaction-library"` to your shell profile
- Windows (PowerShell): `[Environment]::SetEnvironmentVariable("REACTION_LIBRARY", "$HOME\Dropbox\reaction-library", "User")`

The index stores relative paths, so one synced library works on every OS.

## Commands

Your assistant runs these for you. You can also run them yourself:

```
uv run skills/reaction-library/scripts/reaction_library.py <command>
```

| Command | What it does |
|---|---|
| `init` | Create an empty library |
| `ingest <paths> [--move]` | Copy files or folders in, skipping duplicates |
| `list [--status S]` | List entries (`untagged`, `tagged`, `reviewed`) |
| `frames <id>` | Extract keyframes for tagging |
| `tag <id> <file or ->` | Save a tag payload (JSON file, or `-` for stdin) |
| `review <ids>` | Mark tags as approved |
| `retag <ids> \| --all \| --status S` | Clear tags so they get redone |
| `rebuild [--prune]` | Reconcile the index with `media/` |
| `clean-frames [--all]` | Delete leftover keyframes (`--all` includes untagged entries) |
| `search "<moment>" [--emotion T] [--humor T] [--kind K] [--limit N] [--exclude IDS] [--format brief\|full]` | Find candidates |
| `get <id>` | Show one entry |
| `catalog [--brief] [--max N] [--emotion T] [--humor T] [--kind K]` | One line per tagged entry |
| `doctor` | Check your setup |

The humor and emotion terms are in [`skills/reaction-library/vocabulary.json`](skills/reaction-library/vocabulary.json). Search synonyms and phrases are in [`skills/reaction-library/synonyms.json`](skills/reaction-library/synonyms.json); add your own freely.

### How retrieval works

For libraries up to 300 tagged entries, the assistant reads `catalog --brief` (about 45 tokens per entry) once per conversation and picks by meaning, which handles moods and vague requests better than keyword search. Past that size the brief catalog declines and the assistant uses `search` instead. To change the cut-off, set `REACTION_CATALOG_MAX`, for example `export REACTION_CATALOG_MAX=500`.

## Development

```
uv run pytest
```

CI runs the tests on macOS, Linux, and Windows.

## License

MIT
