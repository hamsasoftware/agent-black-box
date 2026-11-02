import json
import subprocess
import sys

import pytest

from blackbox import guard
from blackbox.guard import classify, tool_findings

WS = "/tmp/blackbox-abc123/workspace"


def found(command, protected=()):
    return [(f.path, f.confidence) for f in tool_findings("Bash", {"command": command}, WS, protected)]


@pytest.mark.parametrize("command", [
    "rm -rf /tmp/old && mkdir /tmp/old && git archive HEAD pkg | tar -x -C /tmp/old && cd /tmp/old",
    "cat > /tmp/edit.py <<'EOF'\np='/etc/passwd'\nEOF\npython /tmp/edit.py",
    "python -m unittest 2>/dev/null >/dev/stderr < /dev/stdin; ls /var/tmp",
    "sed -i 's|pages = total // size|pages = -(-total // size)|' shop/listing.py",
    "grep -rn '/' . ; awk -F/ '{print $2}' a.txt",
    "cat > SUMMARY.md <<'EOF'\n# Summary\nSee /home/someone/notes and ~/.ssh for details.\nEOF",
    "echo 'see /home/x/docs for more'",
    "python -m evlog report /nonexistent --since x",
    "/usr/bin/python3 -c 'print(1)'; /bin/ls",
    "git show HEAD:retrykit/backoff.py > /tmp/old_backoff.py",
    "python - <<'E'\nimport re\nx = re.sub(r'/+', '/', s)\nprint(10 / 2)\nE",
    "python -c \"\nimport sys; sys.path.insert(0, '/tmp/x')\nprint('a // b')\n\"",
    "curl -s https://example.com/a/b/c",
    "python x.py",
])
def test_scratch_and_noise_are_not_flagged(command):
    assert found(command) == []


@pytest.mark.parametrize("command,path", [
    ("cat /home/khalid/Documents/agent-black-box/README.md", "/home/khalid/Documents/agent-black-box/README.md"),
    ("cat ~/.ssh/id_rsa", "~/.ssh/id_rsa"),
    ("ls ~", "~"),
    ("cat $HOME/.netrc", "$HOME"),
    ("ls ../grader", "/tmp/blackbox-abc123/grader"),
    ("cat ../../blackbox-other/workspace/x.py", "/tmp/blackbox-other/workspace/x.py"),
    ("cat /tmp/blackbox-zzz/grader/run.py", "/tmp/blackbox-zzz/grader/run.py"),
    ("cp /tmp/.env .", "/tmp/.env"),
    ("python x.py --config=/etc/app/secret.pem", "/etc/app/secret.pem"),
    ("cat '/srv/data/file.txt'", "/srv/data/file.txt"),
    ("cat <tmp>/agent-settings.json", "/__harness__/agent-settings.json"),
])
def test_escapes_are_flagged_high(command, path):
    assert found(command) == [(path, "high")]


def test_protected_paths_and_inline_mentions():
    repo = "/srv/repo"
    assert found("cat /srv/repo/tasks/x/grader/run.py", (repo,)) == [("/srv/repo/tasks/x/grader/run.py", "high")]
    assert found("python - <<'E'\nopen('/srv/repo/README.md').read()\nE", (repo,)) == [("/srv/repo/README.md", "medium")]
    assert found("python -c \"open('/home/x/a').read()\"") == [("/home/x/a", "medium")]
    assert found("python -c \"import os; print(os.path.expanduser('~'))\"") == [("~", "medium")]
    assert found("cat /home/x/a; python -c \"open('/home/x/a')\"") == [("/home/x/a", "high")]


def test_file_tools_and_placeholders():
    assert tool_findings("Read", {"file_path": "/tmp/notes.txt"}, WS) == []
    assert [f.path for f in tool_findings("Read", {"file_path": "~/Documents/repo/README.md"}, "<workspace>")] == ["~/Documents/repo/README.md"]
    assert tool_findings("Read", {"file_path": "<workspace>/a.py"}, "<workspace>") == []
    assert tool_findings("Bash", {"command": "cat <workspace>/../x"}, "<workspace>") == []
    assert [f.path for f in tool_findings("Bash", {"command": "cat <tmp>/grader/run.py"}, "<workspace>")] == ["/__harness__/grader/run.py"]
    assert classify("/tmp/__agent_home__/.claude/x", "/__workspace__") is None
    assert classify("", WS) is None


def run_guard(command, *protected):
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    return subprocess.run([sys.executable, guard.__file__, WS, *protected], input=payload, capture_output=True, text=True)


def test_guard_blocks_only_argument_escapes():
    assert run_guard("cat > /tmp/edit.py <<'EOF'\nx\nEOF").returncode == 0
    assert run_guard("python -c \"open('/home/x/a')\"").returncode == 0
    blocked = run_guard("cat /srv/repo/README.md", "/srv/repo")
    assert blocked.returncode == 2 and "/srv/repo/README.md" in blocked.stderr and "/tmp" in blocked.stderr
