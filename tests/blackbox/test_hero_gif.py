import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("make_hero_gif", ROOT / "scripts" / "make_hero_gif.py")
hero = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hero)


def fake_capture(calls):
    def capture(chrome, page, out, millis, attempts=3):
        calls.append((out.name, millis))
        out.write_bytes(b"png")
    return capture


def test_frame_count_covers_every_station_and_the_hold():
    assert hero.frame_count() == int((sum(hero.DURATIONS) + hero.HOLD) * hero.FPS)
    assert hero.frame_count() == 212


def test_ffmpeg_command_reads_the_frames_and_loops_forever(tmp_path):
    command = hero.ffmpeg_command(tmp_path / "frames", tmp_path / "out.gif")
    assert command[0] == "ffmpeg"
    assert command[command.index("-framerate") + 1] == str(hero.FPS)
    assert command[command.index("-i") + 1] == str(tmp_path / "frames" / "f%04d.png")
    assert command[command.index("-loop") + 1] == "0"
    assert command[-1] == str(tmp_path / "out.gif")
    graph = command[command.index("-vf") + 1]
    assert "palettegen" in graph and "paletteuse" in graph


def test_missing_browser_is_a_clear_exit(monkeypatch):
    monkeypatch.setattr(hero.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit, match="Chrome or Chromium"):
        hero.chrome_binary()


def test_browser_is_found_by_any_known_name(monkeypatch):
    monkeypatch.setattr(hero.shutil, "which", lambda name: "/usr/bin/chromium" if name == "chromium" else None)
    assert hero.chrome_binary() == "/usr/bin/chromium"


def test_build_captures_every_frame_then_encodes(monkeypatch, tmp_path):
    calls, ran = [], []
    monkeypatch.setattr(hero, "chrome_binary", lambda: "chrome")
    monkeypatch.setattr(hero, "capture", fake_capture(calls))
    monkeypatch.setattr(hero.subprocess, "run", lambda command, check: ran.append(command))
    hero.build(tmp_path / "hero.gif", tmp_path / "poster.png", workers=2)
    assert len(calls) == hero.frame_count()
    assert dict(calls)["f0000.png"] == 0
    assert dict(calls)["f0008.png"] == 1000
    assert (tmp_path / "poster.png").read_bytes() == b"png"
    assert ran and ran[0][0] == "ffmpeg"


def test_build_resumes_from_frames_already_on_disk(monkeypatch, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    for index in range(5):
        (work / f"f{index:04d}.png").write_bytes(b"old")
    calls = []
    monkeypatch.setattr(hero, "chrome_binary", lambda: "chrome")
    monkeypatch.setattr(hero, "capture", fake_capture(calls))
    monkeypatch.setattr(hero.subprocess, "run", lambda command, check: None)
    hero.build(tmp_path / "hero.gif", tmp_path / "poster.png", workers=2, work=work)
    assert len(calls) == hero.frame_count() - 5
    assert all(name not in {f"f{index:04d}.png" for index in range(5)} for name, _ in calls)
    assert (work / "hero.html").is_file()


def test_capture_retries_a_hung_browser_then_succeeds(monkeypatch, tmp_path):
    attempts = []

    def run(command, **kwargs):
        attempts.append(command)
        if len(attempts) == 1:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        Path(next(arg for arg in command if arg.startswith("--screenshot=")).split("=", 1)[1]).write_bytes(b"png")

    monkeypatch.setattr(hero.subprocess, "run", run)
    out = tmp_path / "f.png"
    hero.capture("chrome", tmp_path / "page.html", out, 1500)
    assert out.is_file() and len(attempts) == 2
    profiles = {arg for command in attempts for arg in command if arg.startswith("--user-data-dir=")}
    assert len(profiles) == 2
    assert any(arg.endswith("?t=1500") for arg in attempts[-1])


def test_capture_gives_up_after_the_last_attempt(monkeypatch, tmp_path):
    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(hero.subprocess, "run", run)
    with pytest.raises(subprocess.TimeoutExpired):
        hero.capture("chrome", tmp_path / "page.html", tmp_path / "f.png", 0, attempts=2)


def test_main_passes_options_to_build(monkeypatch, tmp_path, capsys):
    seen = {}
    monkeypatch.setattr(hero, "build", lambda output, poster, work=None: seen.update(output=output, poster=poster, work=work))
    assert hero.main(["--output", str(tmp_path / "a.gif"), "--poster", str(tmp_path / "p.png"), "--work", str(tmp_path / "w")]) == 0
    assert seen == {"output": tmp_path / "a.gif", "poster": tmp_path / "p.png", "work": tmp_path / "w"}
    assert "a.gif" in capsys.readouterr().out


def test_the_template_is_an_illustration_and_names_no_vendor_or_person():
    text = hero.TEMPLATE.read_text(encoding="utf-8")
    assert "Illustration, not a recording" in text
    assert not re.search(r"claude|anthropic|openai", text, re.IGNORECASE)
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)


def test_the_committed_assets_stay_small_enough_for_a_readme():
    gif = ROOT / "docs" / "assets" / "hero.gif"
    assert gif.is_file() and gif.stat().st_size < 3_000_000
    assert gif.read_bytes()[:6] in (b"GIF87a", b"GIF89a")
