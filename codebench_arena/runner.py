"""Run a submission's hidden test cases in a resource-limited subprocess."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    import resource
except ImportError:  # Not available on Windows.
    resource = None

SUITE_TIMEOUT_SECONDS = 20

# Runs inside the child process with `python -I`. Kept as text so that it is
# copied beside the submission and never imports this package.
HARNESS = r"""
import contextlib, copy, importlib.util, io, json, signal, socket, sqlite3, sys

def blocked(*args, **kwargs):
    raise PermissionError("network access is disabled during grading")
socket.socket = blocked
socket.create_connection = blocked

def on_alarm(signum, frame):
    raise TimeoutError("case exceeded 2 seconds")
signal.signal(signal.SIGALRM, on_alarm)

def users_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    conn.executemany("INSERT INTO users VALUES (?, ?)", [(1, "alice"), (2, "bob"), (3, "o'brien")])
    return conn

FIXTURES = {"users_db": users_db}

def normalize(value):
    return json.loads(json.dumps(value, default=list))

def run_case(function, case, fixture):
    args = copy.deepcopy(case["args"])
    original = copy.deepcopy(args)
    call_args = ([FIXTURES[fixture]()] if fixture else []) + args
    try:
        signal.alarm(2)
        result = function(*call_args)
        signal.alarm(0)
    except BaseException as exc:
        signal.alarm(0)
        if "raises" in case and type(exc).__name__ == case["raises"]:
            return None
        return f"raised {type(exc).__name__}: {exc}"
    if "raises" in case:
        return f"expected {case['raises']}, returned {result!r}"
    if case.get("no_mutation") and args != original:
        return "mutated its input"
    if normalize(result) != case["expect"]:
        return f"expected {case['expect']!r}, got {result!r}"
    return None

def main():
    task = json.load(open(sys.argv[1], encoding="utf-8"))
    out = {"core": {}, "edge": {}}
    all_cases = [("core", c) for c in task["core"]] + [("edge", c) for c in task["edge"]]
    sink = io.StringIO()
    try:
        with contextlib.redirect_stdout(sink):
            spec = importlib.util.spec_from_file_location("solution", sys.argv[2])
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            function = getattr(module, task["function"])
    except BaseException as exc:
        message = f"import failed: {type(exc).__name__}: {exc}"
        for group, case in all_cases:
            out[group][case["name"]] = message
    else:
        with contextlib.redirect_stdout(sink):
            for group, case in all_cases:
                out[group][case["name"]] = run_case(function, case, task.get("fixture"))
    with open(sys.argv[3], "w", encoding="utf-8") as handle:
        json.dump(out, handle)

main()
"""


@dataclass
class TestOutcome:
    core: dict[str, str | None]
    edge: dict[str, str | None]
    fatal: str | None = None


def _limit_resources() -> None:
    if resource is not None:
        resource.setrlimit(resource.RLIMIT_CPU, (15, 15))
        resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))


def run_tests(task: dict, source: str) -> TestOutcome:
    """Grade ``source``. Each outcome maps a case name to None (pass) or a reason.

    This limits accidents, but it is not a security boundary. Run untrusted
    submissions inside a container with networking disabled.
    """
    with tempfile.TemporaryDirectory(prefix="codebench-") as temp:
        folder = Path(temp)
        (folder / "harness.py").write_text(HARNESS, encoding="utf-8")
        (folder / "solution.py").write_text(source, encoding="utf-8")
        (folder / "task.json").write_text(json.dumps(task), encoding="utf-8")
        results = folder / "results.json"
        command = [sys.executable, "-I", "harness.py", "task.json", "solution.py", str(results)]
        try:
            subprocess.run(
                command,
                cwd=folder,
                env={"PATH": os.environ.get("PATH", "")},
                capture_output=True,
                timeout=SUITE_TIMEOUT_SECONDS,
                preexec_fn=_limit_resources if resource is not None else None,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _all_failed(task, f"test suite exceeded {SUITE_TIMEOUT_SECONDS}s")
        if not results.exists():
            return _all_failed(task, "submission crashed the test process")
        data = json.loads(results.read_text(encoding="utf-8"))
    return TestOutcome(data["core"], data["edge"])


def _all_failed(task: dict, reason: str) -> TestOutcome:
    return TestOutcome(
        {case["name"]: reason for case in task["core"]},
        {case["name"]: reason for case in task["edge"]},
        fatal=reason,
    )
