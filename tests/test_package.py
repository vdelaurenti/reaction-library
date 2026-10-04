import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "reaction-library" / "scripts" / "reaction_library.py"
COMMANDS = ["init", "ingest", "list", "frames", "tag", "tag-batch", "review", "retag", "rebuild", "clean-frames", "search", "get", "catalog", "doctor"]


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


def test_entry_script_runs_directly_through_uv():
    lines = SCRIPT.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "#!/usr/bin/env -S uv run --script"
    assert lines[1] == "# /// script"


def test_entry_script_is_executable_in_git():
    """Checks the mode git records, so it holds on Windows checkouts too."""
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")
    out = subprocess.run(["git", "ls-files", "-s", SCRIPT.relative_to(ROOT).as_posix()],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    assert out.startswith("100755"), out


def test_skill_covers_first_run():
    text = (ROOT / "skills" / "reaction-library" / "SKILL.md").read_text(encoding="utf-8")
    assert "## First run" in text
    assert "No library at" in text
    assert "untagged waiting to be tagged" in text
    assert "batches of 10" in text


def test_readme_manual_install_clones_first():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "git clone https://github.com/vdelaurenti/reaction-library" in text
    assert "## Your first five minutes" in text


def test_skill_explains_missing_uv():
    text = (ROOT / "skills" / "reaction-library" / "SKILL.md").read_text(encoding="utf-8")
    assert "brew install uv" in text
    assert "winget install --id=astral-sh.uv -e" in text
    assert "astral.sh/uv/install.sh" in text
    assert "plain `python`" in text
