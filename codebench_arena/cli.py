"""Command-line interface: ``codebench --tasks tasks --submissions submissions``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .arena import discover_submissions, load_tasks, run_arena
from .report import render_html


def main(argv: list[str] | None = None) -> int:
    """Return 0 on success, 1 if a model is below --min-score, 2 on bad input."""
    parser = argparse.ArgumentParser(prog="codebench", description="Benchmark LLM-written code.")
    parser.add_argument("--tasks", type=Path, default=Path("tasks"))
    parser.add_argument("--submissions", type=Path, default=Path("submissions"))
    parser.add_argument("--html", type=Path)
    parser.add_argument("--json", type=Path, dest="json_path")
    parser.add_argument("--min-score", type=float, help="fail if any model scores below this")
    args = parser.parse_args(argv)

    try:
        tasks = load_tasks(args.tasks)
        submissions = discover_submissions(args.submissions)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not tasks or not submissions:
        print("error: found no tasks or no submissions", file=sys.stderr)
        return 2

    results = run_arena(tasks, submissions)
    for rank, row in enumerate(results["leaderboard"], start=1):
        print(f"#{rank}  {row['score']:>5.1f}  {row['model']}")
    for item in results["calibration"]:
        print(f"task  {item['task']:<18} mean {item['mean']:>5.1f}  spread {item['spread']:>5.1f}  {item['verdict']}")
    if args.html:
        args.html.write_text(render_html(results), encoding="utf-8")
    if args.json_path:
        args.json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    if args.min_score is not None and any(row["score"] < args.min_score for row in results["leaderboard"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
