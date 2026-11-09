"""Static checks that catch failures tests can miss, without running the code."""

from __future__ import annotations

import ast
import importlib
import re
import sys
from dataclasses import dataclass, field

BRANCHES = (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.IfExp, ast.comprehension)
SECRET_NAME = re.compile(r"password|passwd|secret|api_?key|token", re.I)
UNSAFE_TO_IMPORT = {"antigravity", "this", "idlelib", "tkinter", "turtle", "turtledemo"}


@dataclass
class StaticReport:
    syntax_error: str | None = None
    has_function: bool = False
    hallucinations: list[str] = field(default_factory=list)
    security: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    complexity: int = 0


def _load_stdlib(name: str):
    root = name.split(".")[0]
    if root in UNSAFE_TO_IMPORT or root not in sys.stdlib_module_names:
        return None
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def _rebound_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
    return names


def _check_imports(tree: ast.AST, task: dict, report: StaticReport) -> None:
    allowed = set(task.get("allowed_imports", []))
    forbidden = set(task.get("forbidden_imports", []))
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                _classify(root, allowed, forbidden, report)
                if root in sys.stdlib_module_names and (alias.asname or "." not in alias.name):
                    aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            root = node.module.split(".")[0]
            _classify(root, allowed, forbidden, report)
            module = _load_stdlib(node.module)
            if module is not None:
                for alias in node.names:
                    if alias.name != "*" and not hasattr(module, alias.name) and _load_stdlib(f"{node.module}.{alias.name}") is None:
                        report.hallucinations.append(f"line {node.lineno}: {node.module} has no '{alias.name}'")

    rebound = _rebound_names(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases and node.value.id not in rebound:
            module = _load_stdlib(aliases[node.value.id])
            if module is not None and not hasattr(module, node.attr):
                report.hallucinations.append(f"line {node.lineno}: {aliases[node.value.id]}.{node.attr} does not exist")


def _classify(root: str, allowed: set[str], forbidden: set[str], report: StaticReport) -> None:
    if root in forbidden:
        report.constraints.append(f"imports forbidden package '{root}'")
    elif root not in sys.stdlib_module_names and root not in allowed:
        report.hallucinations.append(f"imports '{root}', which is neither stdlib nor an allowed dependency")


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ""


def _is_built_string(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(part, ast.FormattedValue) for part in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return True
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format"


def _check_security(tree: ast.AST, report: StaticReport) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _dotted(node.func)
            if name in {"eval", "exec", "os.system", "pickle.loads", "marshal.loads"}:
                report.security.append(f"line {node.lineno}: unsafe call to {name}()")
            shell = any(kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in node.keywords)
            if name.startswith("subprocess.") and shell:
                report.security.append(f"line {node.lineno}: subprocess call with shell=True")
            if isinstance(node.func, ast.Attribute) and node.func.attr in {"execute", "executemany"} and node.args and _is_built_string(node.args[0]):
                report.security.append(f"line {node.lineno}: SQL built with string formatting (injection risk)")
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and node.value.value:
            for target in node.targets:
                if isinstance(target, ast.Name) and SECRET_NAME.search(target.id):
                    report.security.append(f"line {node.lineno}: hardcoded credential in '{target.id}'")


def _complexity(function: ast.AST) -> int:
    score = 1
    for node in ast.walk(function):
        if isinstance(node, BRANCHES):
            score += 1
        elif isinstance(node, ast.BoolOp):
            score += len(node.values) - 1
    return score


def analyze(source: str, task: dict) -> StaticReport:
    report = StaticReport()
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError) as exc:
        report.syntax_error = str(exc)
        return report
    report.has_function = any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == task["function"] for node in tree.body)
    _check_imports(tree, task, report)
    _check_security(tree, report)
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    report.complexity = max((_complexity(function) for function in functions), default=0)
    limit = task.get("max_complexity")
    if limit is not None and report.complexity > limit:
        report.constraints.append(f"cyclomatic complexity {report.complexity} exceeds limit {limit}")
    return report
