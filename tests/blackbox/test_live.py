import io
import json
import re

import pytest

from blackbox import live, runner
from blackbox.cli import main
from blackbox.live import LiveView, resolve_run, tool_summary, watch
from conftest import FAKE_KEY, FIXTURES

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def plain_view(width=120):
    out = io.StringIO()
    return LiveView(out=out, tty=False, color=False, width=width), out


class Recorder:
    def __init__(self, root):
        self.root = root
        self.checks = []
        self.run_dir = None

    def header(self, meta):
        self.run_dir = self.root / "runs" / meta["run_id"]

    def line(self, text, style=None):
        pass

    def event(self, i, t_ms, ev):
        lines = (self.run_dir / "events.jsonl").read_text().splitlines()
        self.checks.append((i, len(lines), json.loads(lines[-1])["i"], (self.run_dir / "live.json").is_file(),
                            (self.run_dir / "run.json").exists()))

    def start_clock(self):
        pass

    def stop_clock(self):
        pass

    def summary(self, record, run_dir):
        self.summary_record = record


def test_events_are_written_as_they_arrive(do_run, root):
    rec_view = Recorder(root)
    run_dir, rec, _ = do_run("success", view=rec_view)
    assert rec_view.checks and all(i + 1 == n and last == i and live_file and not done
                                   for i, n, last, live_file, done in rec_view.checks)
    assert not (run_dir / "live.json").exists()
    assert rec_view.summary_record["run_id"] == rec["run_id"]
    assert len((run_dir / "events.jsonl").read_text().splitlines()) == rec["event_count"]


def test_failed_run_marks_live_file(do_run, root, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("grader exploded")
    monkeypatch.setattr(runner, "run_grader", boom)
    with pytest.raises(RuntimeError):
        do_run("success")
    run_dir = next((root / "runs").iterdir())
    assert json.loads((run_dir / "live.json").read_text())["status"] == "failed"
    assert (run_dir / "events.jsonl").read_text().strip()


def test_plain_view_of_a_run(do_run):
    view, out = plain_view()
    _, rec, _ = do_run("success", view=view)
    text = out.getvalue()
    assert not ANSI.search(text) and "\r" not in text
    assert all(len(l) <= 119 for l in text.splitlines())
    head = text.splitlines()[1]
    for part in ("Ember", rec["agent_id"], "demo-add", "bare", "claude-sonnet-5-5"):
        assert part in head
    assert "budget $0.75" in text and "max turns 12" in text
    assert "* session start" in text
    assert "> Read" in text and "calc.py" in text and "<workspace>" not in text.split("> Read")[1].splitlines()[0]
    assert "> Edit   calc.py  (-1 +1 lines)" in text
    assert "> Bash   python -m pytest -q" in text
    assert "< ok Bash 2 lines" in text
    assert '" Fixed the bug in calc.py' in text
    assert "# agent finished: success  4 turns  $0.0123" in text
    assert "turns 4/12" in text and "cost $0.0123 / $0.75" in text
    assert "grade PASS" in text and "+verified-before-claiming" in text
    assert "claims" in text and "recorded in" in text


def test_denial_and_hook_block_highlighted(do_run):
    view, out = plain_view()
    do_run("denied", view=view)
    assert "DENIED Bash: Claude requested permissions" in out.getvalue()
    assert "blocked 1" in out.getvalue()
    view, out = plain_view()
    do_run("hookblock", view=view)
    assert "BLOCKED by hook Bash: PreToolUse:Bash hook error" in out.getvalue()


def test_view_never_shows_secrets(do_run):
    view, out = plain_view()
    do_run("leak", view=view)
    text = out.getvalue()
    assert FAKE_KEY not in text and "example.org" not in text and "/home/someone" not in text
    assert "[REDACTED:env]" in text
    view, out = plain_view()
    view.event(0, 5, {"type": "assistant", "message": {"id": "m", "content": [
        {"type": "text", "text": "token " + "ghp_" + "Q" * 36 + " mail a" + "@" + "b.example.com"}]}})
    assert "ghp_" not in out.getvalue() and "example.com" not in out.getvalue()


def test_tty_view_uses_ansi_and_footer(do_run):
    out = io.StringIO()
    view = LiveView(out=out, tty=True, color=True, width=120)
    do_run("success", view=view)
    text = out.getvalue()
    assert "\x1b[" in text and "\r\x1b[K" in text
    visible = ANSI.sub("", text)
    assert "cost $0.0123 / $0.75" in visible


def test_truncation_and_narrow_terminal():
    view, out = plain_view(width=60)
    view.event(3, 1500, {"type": "assistant", "message": {"id": "m", "content": [
        {"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": "python -c '" + "x" * 300 + "'"}}]}})
    line = out.getvalue().splitlines()[0]
    assert len(line) == 59 and line.endswith("...")
    assert line.startswith("   3    1.5s  > Bash")


def test_tool_summaries():
    assert tool_summary("Write", {"file_path": "<workspace>/a/b.py", "content": "1\n2\n"}) == "a/b.py  (2 lines)"
    assert tool_summary("Grep", {"pattern": "def x", "path": "<workspace>"}) == "def x in ."
    assert tool_summary("Glob", {"pattern": "**/*.py"}) == "**/*.py"
    assert tool_summary("Task", {"description": "look\naround"}) == "look around"
    assert tool_summary("Other", {"k": 1}) == '{"k": 1}'
    assert tool_summary("Bash", "x") == ""


def test_view_of_other_events():
    view, out = plain_view()
    view.event(0, None, {"type": "system", "subtype": "thinking_tokens"})
    view.event(1, None, {"type": "system", "subtype": "compact_boundary"})
    view.event(2, None, {"type": "malformed", "raw": "not json {"})
    view.event(3, None, {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": ""}]}})
    view.event(4, None, {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "z",
                                                                   "is_error": True, "content": "boom"}]}})
    view.event(5, None, {"type": "result", "subtype": "success", "is_error": True, "terminal_reason": "api_error"})
    view.event(6, None, {"type": "user", "message": {"content": "plain"}})
    view.event(7, None, {"type": "weird"})
    text = out.getvalue()
    assert "thinking_tokens" not in text
    assert "* compact_boundary" in text and "! malformed line  not json {" in text and "~ thinking" in text
    assert "< error tool: boom" in text and "agent finished: api_error" in text
    view.summary({"grade": {"passed": False, "score": 0, "checks": [{"name": "c1", "passed": False, "detail": "bad"}],
                            "error": "grader timed out"}, "cost_usd": None, "behaviours": []})
    text = out.getvalue()
    assert "grade FAIL" in text and "failed check c1  bad" in text and "grader error grader timed out" in text
    assert "cost n/a" in text and "behaviours none tagged" in text


def test_watch_finished_run_and_replay(do_run, root):
    run_dir, rec, _ = do_run("success")
    view, out = plain_view()
    assert watch(run_dir, view, follow=False) == 0
    text = out.getvalue()
    assert "Ember" in text and "> Bash   python -m pytest -q" in text and "grade PASS" in text
    sleeps = []
    view, _ = plain_view()
    watch(run_dir, view, replay=2.0, sleep=sleeps.append)
    assert len(sleeps) == rec["event_count"] and all(0 <= s <= 2.0 for s in sleeps)


def test_watch_follows_a_live_run(tmp_path):
    run_dir = tmp_path / "runs" / "20261102T000000Z-t-bare-ember"
    run_dir.mkdir(parents=True)
    meta = {"run_id": run_dir.name, "agent_id": "agt-12345678", "agent_name": "Ember", "task_id": "t",
            "variant": "bare", "model": "m", "budget_usd": 0.5, "max_turns": 5, "status": "running"}
    (run_dir / "live.json").write_text(json.dumps(meta))
    ev = {"type": "assistant", "message": {"id": "m1", "content": [{"type": "text", "text": "step one"}]}}
    first = json.dumps({"i": 0, "t_ms": 10, "event": ev})
    (run_dir / "events.jsonl").write_text(first + "\n" + first[:15])
    steps = []

    def fake_sleep(_):
        steps.append(1)
        if len(steps) == 1:
            with (run_dir / "events.jsonl").open("a") as fh:
                fh.write(first[15:].replace("step one", "step two").replace('"i": 0', '"i": 1') + "\n")
        elif len(steps) == 2:
            (run_dir / "run.json").write_text(json.dumps({**meta, "grade": {"passed": True, "score": 1, "checks": []},
                                                          "behaviours": [{"id": "minimal-diff", "polarity": "good"}]}))
            (run_dir / "live.json").unlink()

    view, out = plain_view()
    assert watch(run_dir, view, sleep=fake_sleep) == 0
    text = out.getvalue()
    assert text.count("step one") == 1 and text.count("step two") == 1
    assert "grade PASS" in text and "+minimal-diff" in text


def test_watch_stops_on_failure_or_timeout(tmp_path):
    run_dir = tmp_path / "r"
    run_dir.mkdir()
    (run_dir / "live.json").write_text(json.dumps({"run_id": "r", "status": "failed"}))
    view, out = plain_view()
    assert watch(run_dir, view, sleep=lambda s: None) == 1
    assert "status failed" in out.getvalue()
    (run_dir / "live.json").write_text(json.dumps({"run_id": "r", "status": "running"}))
    view, out = plain_view()
    assert watch(run_dir, view, timeout=0.4, poll=0.2, sleep=lambda s: None) == 1
    assert "timeout" in out.getvalue()
    view, out = plain_view()
    assert watch(run_dir, view, follow=False) == 1
    (run_dir / "live.json").write_text("{broken")
    assert live.read_meta(run_dir) == ({"run_id": "r"}, False)


def test_resolve_and_cli_watch(do_run, root, capsys):
    run_dir, rec, _ = do_run("success")
    assert resolve_run(str(run_dir), root) == run_dir
    assert resolve_run(rec["run_id"], root) == run_dir
    assert resolve_run("bare-ember", root) == run_dir
    with pytest.raises(FileNotFoundError):
        resolve_run("nothing-like-this", root)
    capsys.readouterr()
    assert main(["watch", "ember", "--root", str(root), "--no-color"]) == 0
    out = capsys.readouterr().out
    assert "grade PASS" in out and "\x1b[" not in out
    assert main(["watch", "zzz", "--root", str(root)]) == 2


def test_cli_run_live(root, task_dir, env_file, capsys):
    code = main(["run", str(task_dir), "--variant", "bare", "--model", "m", "--sandbox", "off", "--live",
                 "--root", str(root), "--env-file", str(env_file), "--agent-cli", str(FIXTURES / "fake_agent.py")])
    out = capsys.readouterr().out
    assert code == 0 and "agent Ember" in out.replace("  ", " ") and "grade" in out
    assert FAKE_KEY not in out


def test_clock_redraws_footer_on_a_tty():
    import time
    out = io.StringIO()
    view = LiveView(out=out, tty=True, color=False, width=100)
    view.start_clock(interval=0.02)
    time.sleep(0.15)
    view.stop_clock()
    text = out.getvalue()
    assert text.count("\r\x1b[K") >= 2 and "elapsed 0." in text
    quiet = LiveView(out=io.StringIO(), tty=False)
    quiet.start_clock()
    quiet.stop_clock()
    assert quiet.out.getvalue() == ""
