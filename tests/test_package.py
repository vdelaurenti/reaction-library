import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = ["init", "ingest", "list", "frames", "tag", "review", "retag", "rebuild", "search", "get", "catalog", "doctor"]


def test_skill_frontmatter():
    text = (ROOT / "skills" / "reaction-library" / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert match, "SKILL.md must start with YAML frontmatter"
    frontmatter = match.group(1)
    assert re.search(r"^name: reaction-library$", frontmatter, re.M)
    description = re.search(r"^description: (.+)$", frontmatter, re.M)
    assert description and len(description.group(1)) <= 1024


def test_skill_documents_every_command():
    text = (ROOT / "skills" / "reaction-library" / "SKILL.md").read_text(encoding="utf-8")
    for command in COMMANDS:
        assert f"`{command}" in text, f"SKILL.md does not mention `{command}`"


def test_plugin_manifests_agree():
    plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert plugin["name"] == "reaction-library"
    assert marketplace["name"] == "reaction-library"
    [entry] = marketplace["plugins"]
    assert entry["name"] == plugin["name"] and entry["source"] == "./"
