#!/usr/bin/env python3
"""Render docs/assets/hero.gif from the 3D illustration in docs/assets/hero/template.html.

The animation is an illustration of how the repository works, not a recording. It needs
Google Chrome (or Chromium) and ffmpeg. The page draws itself for any time given as ?t=MILLISECONDS.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "docs" / "assets" / "hero" / "template.html"
DURATIONS = (4.4, 5.6, 5.2, 4.6, 5.0)
HOLD = 1.8
FPS = 8
WIDTH = 1000
HEIGHT = 560


def frame_count() -> int:
    return int((sum(DURATIONS) + HOLD) * FPS)


def chrome_binary() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    raise SystemExit("hero: Google Chrome or Chromium is required")


def capture(chrome: str, page: Path, out: Path, millis: int, attempts: int = 3) -> None:
    for attempt in range(attempts):
        with tempfile.TemporaryDirectory() as profile:
            try:
                subprocess.run(
                    [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                     f"--user-data-dir={profile}", f"--window-size={WIDTH},{HEIGHT}", "--virtual-time-budget=400",
                     f"--screenshot={out}", f"file://{page}?t={millis}"],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
                if out.is_file():
                    return
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
                if attempt == attempts - 1:
                    raise


def ffmpeg_command(frames_dir: Path, output: Path) -> list[str]:
    graph = ("scale=560:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=32:stats_mode=diff[p];"
             "[b][p]paletteuse=dither=none:diff_mode=rectangle")
    return ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(frames_dir / "f%04d.png"),
            "-vf", graph, "-loop", "0", str(output)]


def build(output: Path, poster: Path, workers: int = 6, work: Path | None = None) -> None:
    chrome = chrome_binary()
    total = frame_count()
    with tempfile.TemporaryDirectory() as tmp:
        frames = work if work is not None else Path(tmp)
        frames.mkdir(parents=True, exist_ok=True)
        page = frames / "hero.html"
        shutil.copyfile(TEMPLATE, page)
        todo = [index for index in range(total) if not (frames / f"f{index:04d}.png").is_file()]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(capture, chrome, page, frames / f"f{index:04d}.png", int(index * 1000 / FPS)) for index in todo]
            for future in futures:
                future.result()
        shutil.copyfile(frames / f"f{total - 1:04d}.png", poster)
        subprocess.run(ffmpeg_command(frames, output), check=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(ROOT / "docs" / "assets" / "hero.gif"))
    parser.add_argument("--poster", default=str(ROOT / "docs" / "assets" / "hero-poster.png"))
    parser.add_argument("--work", help="directory for frames; frames already there are reused, so an interrupted build can resume")
    args = parser.parse_args(argv)
    build(Path(args.output), Path(args.poster), work=Path(args.work) if args.work else None)
    print(f"hero: wrote {args.output} and {args.poster}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
