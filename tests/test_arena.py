from pathlib import Path

import pytest

from codebench_arena.arena import calibrate, discover_submissions, grade, load_tasks, run_arena
from codebench_arena.cli import main
from codebench_arena.report import render_html
from codebench_arena.runner import run_tests
from codebench_arena.static import analyze

ROOT = Path(__file__).resolve().parents[1]
TASKS = {task["id"]: task for task in load_tasks(ROOT / "tasks")}
SUBMISSIONS = discover_submissions(ROOT / "submissions")
TASK = {"function": "f", "core": [{"name": "one", "args": [], "expect": 1}], "edge": [], "id": "t", "prompt": "p"}


def dims(item):
    return {dimension.name: dimension for dimension in item.dimensions}


def sample(model, task):
    return grade(model, TASKS[task], SUBMISSIONS[model][task])


def test_correct_solutions_score_full_marks():
    for task in TASKS:
        assert sample("model-alpha", task).total == 100


def test_static_finds_hallucinated_package():
    assert analyze("import durationkit\ndef f(): pass", TASK).hallucinations


def test_static_finds_hallucinated_stdlib_function_on_untested_path():
    item = sample("model-gamma", "merge_intervals")
    assert dims(item)["correctness"].score == 1
    assert dims(item)["no_hallucination"].score == 0
    assert "math.clamp" in dims(item)["no_hallucination"].justification


def test_local_variable_is_not_mistaken_for_module():
    report = analyze("import math\ndef f(math):\n    return math.clamp", TASK)
    assert not report.hallucinations


def test_valid_stdlib_use_is_clean():
    report = analyze("import json\nfrom os import path\ndef f():\n    return json.dumps({}), path.sep", TASK)
    assert not report.hallucinations


def test_from_import_of_missing_name_is_flagged():
    assert analyze("from json import parse\ndef f(): pass", TASK).hallucinations


@pytest.mark.parametrize(
    "code",
    [
        "def f(x): return eval(x)",
        "import os\ndef f(x): os.system(x)",
        "import subprocess\ndef f(x): subprocess.run(x, shell=True)",
        "def f(c, x): c.execute(f'select {x}')",
        "def f(c, x): c.execute('select ' + x)",
        "def f(c, x): c.execute('select {}'.format(x))",
        "API_KEY = 'abc123'\ndef f(): pass",
    ],
)
def test_security_patterns(code):
    assert analyze(code, TASK).security


def test_parameterized_sql_is_clean():
    assert not analyze("def f(c, x): c.execute('select ?', (x,))", TASK).security


def test_sql_injection_loses_points_dynamically_and_statically():
    item = sample("model-beta", "find_user")
    assert dims(item)["security"].score < 1
    assert "injection_returns_nothing" in dims(item)["edge_cases"].justification


def test_eval_solution_is_penalised_even_when_core_passes():
    item = sample("model-gamma", "parse_duration")
    assert dims(item)["correctness"].score == 1 and dims(item)["security"].score < 1


def test_mutation_is_detected():
    item = sample("model-beta", "merge_intervals")
    assert "mutated" in dims(item)["edge_cases"].justification


def test_infinite_loop_is_contained():
    outcome = run_tests(TASK, "def f():\n    while True: pass")
    assert "TimeoutError" in outcome.core["one"]


def test_network_is_blocked():
    source = "import socket\ndef f():\n    socket.socket()\n    return 1"
    assert "PermissionError" in run_tests(TASK, source).core["one"]


def test_printing_cannot_corrupt_results():
    assert run_tests(TASK, "print('noise')\ndef f():\n    print('more')\n    return 1").core["one"] is None


def test_process_crash_is_a_failure():
    outcome = run_tests(TASK, "import os\ndef f():\n    os._exit(3)")
    assert outcome.fatal and outcome.core["one"]


@pytest.mark.parametrize(
    "source, reason",
    [("def broken(:", "Syntax error"), ("def other(): pass", "not defined"), (None, "No submission")],
)
def test_unusable_submissions_score_zero(source, reason):
    item = grade("m", TASK, source)
    assert item.total == 0 and reason in item.dimensions[0].justification


@pytest.mark.parametrize(
    "totals, verdict",
    [([95, 100, 92], "too easy"), ([0, 20, 30], "too hard or broken"), ([50, 52, 55], "not discriminating"), ([100, 40, 70], "discriminating")],
)
def test_calibration(totals, verdict):
    assert calibrate("t", totals).verdict == verdict


def test_reports_rank_models_and_escape_content():
    results = run_arena(list(TASKS.values()), SUBMISSIONS)
    assert results["leaderboard"][0]["model"] == "model-alpha"
    assert {item["task"]: item["verdict"] for item in results["calibration"]}["reverse_words"] == "too easy"
    results["leaderboard"][0]["model"] = "<script>x</script>"
    for item in results["grades"]:
        if item["model"] == "model-alpha":
            item["model"] = "<script>x</script>"
    assert "<script>" not in render_html(results).replace("<style>", "")


def test_cli(tmp_path):
    html = tmp_path / "r.html"
    args = ["--tasks", str(ROOT / "tasks"), "--submissions", str(ROOT / "submissions"), "--html", str(html)]
    assert main(args) == 0 and html.exists()
    assert main([*args, "--min-score", "99"]) == 1
    assert main(["--tasks", str(tmp_path), "--submissions", str(tmp_path)]) == 2
