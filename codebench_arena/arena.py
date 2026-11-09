"""Combine tests and static analysis into auditable scores and task calibration."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .runner import run_tests
from .static import analyze

WEIGHTS = {"correctness": 45, "edge_cases": 25, "security": 15, "no_hallucination": 10, "constraints": 5}


@dataclass
class Dimension:
    name: str
    score: float
    weight: int
    justification: str


@dataclass
class Graded:
    model: str
    task: str
    total: float
    dimensions: list[Dimension]


@dataclass
class Calibration:
    task: str
    mean: float
    spread: float
    verdict: str


def load_tasks(folder: str | Path) -> list[dict]:
    tasks = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(Path(folder).glob("*.json"))]
    for task in tasks:
        missing = {"id", "function", "prompt", "core", "edge"} - task.keys()
        if missing:
            raise ValueError(f"task {task.get('id', '?')} is missing {sorted(missing)}")
    return tasks


def discover_submissions(folder: str | Path) -> dict[str, dict[str, str]]:
    """Map model -> task id -> source, from files named ``<model>__<task>.py``."""
    found: dict[str, dict[str, str]] = {}
    for path in sorted(Path(folder).glob("*__*.py")):
        model, task_id = path.stem.split("__", 1)
        found.setdefault(model, {})[task_id] = path.read_text(encoding="utf-8")
    return found


def _test_dimension(name: str, cases: dict[str, str | None]) -> Dimension:
    failed = {case: reason for case, reason in cases.items() if reason}
    score = (len(cases) - len(failed)) / len(cases) if cases else 1.0
    if failed:
        detail = "; ".join(f"{case}: {reason}" for case, reason in failed.items())
        text = f"{len(cases) - len(failed)}/{len(cases)} passed. Failed: {detail}"
    else:
        text = f"All {len(cases)} cases passed."
    return Dimension(name, score, WEIGHTS[name], text)


def _static_dimension(name: str, issues: list[str], step: float, clean: str) -> Dimension:
    score = max(0.0, 1.0 - step * len(issues))
    return Dimension(name, score, WEIGHTS[name], "; ".join(issues) if issues else clean)


def _zero(model: str, task_id: str, reason: str) -> Graded:
    return Graded(model, task_id, 0.0, [Dimension(name, 0.0, weight, reason) for name, weight in WEIGHTS.items()])


def grade(model: str, task: dict, source: str | None) -> Graded:
    if source is None:
        return _zero(model, task["id"], "No submission.")
    static = analyze(source, task)
    if static.syntax_error:
        return _zero(model, task["id"], f"Syntax error: {static.syntax_error}")
    if not static.has_function:
        return _zero(model, task["id"], f"Required function '{task['function']}' is not defined.")
    outcome = run_tests(task, source)
    dimensions = [
        _test_dimension("correctness", outcome.core),
        _test_dimension("edge_cases", outcome.edge),
        _static_dimension("security", static.security, 0.5, "No unsafe patterns found."),
        _static_dimension("no_hallucination", static.hallucinations, 1.0, "All imports and stdlib attributes exist."),
        _static_dimension("constraints", static.constraints, 0.5, f"Complexity {static.complexity}; constraints met."),
    ]
    total = sum(dimension.score * dimension.weight for dimension in dimensions) / sum(WEIGHTS.values()) * 100
    return Graded(model, task["id"], round(total, 1), dimensions)


def calibrate(task_id: str, totals: list[float]) -> Calibration:
    """Judge the task, not the model: a benchmark item must separate models."""
    mean = sum(totals) / len(totals)
    spread = max(totals) - min(totals)
    if min(totals) >= 90:
        verdict = "too easy"
    elif max(totals) <= 30:
        verdict = "too hard or broken"
    elif spread < 10:
        verdict = "not discriminating"
    else:
        verdict = "discriminating"
    return Calibration(task_id, round(mean, 1), round(spread, 1), verdict)


def run_arena(tasks: list[dict], submissions: dict[str, dict[str, str]]) -> dict:
    grades = [grade(model, task, sources.get(task["id"])) for model, sources in submissions.items() for task in tasks]
    leaderboard = []
    for model in submissions:
        mine = [item for item in grades if item.model == model]
        dims = {name: round(sum(next(d.score for d in item.dimensions if d.name == name) for item in mine) / len(mine) * 100, 1) for name in WEIGHTS}
        leaderboard.append({"model": model, "score": round(sum(item.total for item in mine) / len(mine), 1), "dimensions": dims})
    leaderboard.sort(key=lambda row: -row["score"])
    calibration = [calibrate(task["id"], [item.total for item in grades if item.task == task["id"]]) for task in tasks]
    return {
        "tasks": [{"id": task["id"], "title": task.get("title", task["id"])} for task in tasks],
        "leaderboard": leaderboard,
        "grades": [asdict(item) for item in grades],
        "calibration": [asdict(item) for item in calibration],
    }
