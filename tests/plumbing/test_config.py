import json
import re

import pytest

from conftest import HOOKS, ROOT, VARIANTS

READ_ONLY_AGENTS = {"atlas"}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"}


def load_settings(path):
    return json.loads(path.read_text())


@pytest.mark.parametrize("settings_path", [
    ROOT / ".claude" / "settings.json",
    VARIANTS / "plumbed" / ".claude" / "settings.json",
])
def test_settings_reference_existing_hooks(settings_path):
    settings = load_settings(settings_path)
    base = settings_path.parent.parent
    for matchers in settings["hooks"].values():
        for matcher in matchers:
            for hook in matcher["hooks"]:
                found = re.search(r"\"\$CLAUDE_PROJECT_DIR\"/(\S+)", hook["command"])
                assert found, hook["command"]
                assert (base / found.group(1)).is_file()


def test_root_settings_deny_secrets_and_protected_data():
    deny = set(load_settings(ROOT / ".claude" / "settings.json")["permissions"]["deny"])
    for rule in ("Read(./.env)", "Edit(/runs/**)", "Edit(/ledger/**)", "Bash(git reset --hard*)", "Bash(curl * | sh*)"):
        assert rule in deny


def test_root_permission_lists_do_not_overlap():
    perms = load_settings(ROOT / ".claude" / "settings.json")["permissions"]
    allow, ask, deny = (set(perms[k]) for k in ("allow", "ask", "deny"))
    assert not (allow & ask) and not (allow & deny) and not (ask & deny)


def frontmatter(path):
    text = path.read_text()
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert match, path
    return dict(line.split(": ", 1) for line in match.group(1).splitlines())


@pytest.mark.parametrize("name", ["atlas", "forge", "tally", "gauntlet", "reel"])
def test_subagent_definitions(name):
    meta = frontmatter(ROOT / ".claude" / "agents" / f"{name}.md")
    assert meta["name"] == name
    assert meta["description"]
    tools = {t.strip() for t in meta["tools"].split(",")}
    if name in READ_ONLY_AGENTS:
        assert not (tools & EDIT_TOOLS)


def test_claude_md_imports_agents_md():
    assert (ROOT / "CLAUDE.md").read_text().splitlines()[0] == "@AGENTS.md"
    assert (VARIANTS / "plumbed" / "CLAUDE.md").read_text().strip() == "@AGENTS.md"


def test_bare_variant_is_empty():
    assert sorted(p.name for p in (VARIANTS / "bare").iterdir()) == [".gitkeep"]


def test_plumbed_agents_md_is_compact():
    assert len((VARIANTS / "plumbed" / "AGENTS.md").read_text().splitlines()) <= 40


def test_plumbed_variant_is_neutral():
    forbidden = re.compile(r"black.?box|experiment|bare|plumbed|anthropic|claude(?!_PROJECT_DIR)|openai|gpt|gemini|copilot|cursor", re.I)
    for path in (VARIANTS / "plumbed").rglob("*"):
        if path.is_file() and path.name != "CLAUDE.md":
            text = path.read_text().replace(".claude/", "")
            assert not forbidden.search(text), (path, forbidden.search(text).group(0))


def test_hooks_use_standard_library_only():
    allowed = {"json", "os", "re", "sys", "datetime", "pathlib", "_hooklib"}
    for path in list(HOOKS.glob("*.py")) + list((VARIANTS / "plumbed" / ".claude" / "hooks").glob("*.py")):
        imports = re.findall(r"^(?:from|import)\s+([\w_]+)", path.read_text(), re.M)
        assert set(imports) <= allowed, (path, imports)
