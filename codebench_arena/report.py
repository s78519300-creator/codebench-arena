"""Render arena results as a self-contained HTML leaderboard."""

from __future__ import annotations

from html import escape

STYLE = """
:root{--bg:#07131a;--panel:#10222b;--line:#21414f;--text:#ecfbff;--muted:#8fb0bc;--a:#22d3ee;--b:#a3e635;--bad:#fb7185;--warn:#fbbf24}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(900px 450px at 15% -10%,#155e75 0,transparent 60%),var(--bg);color:var(--text);font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1080px;margin:auto;padding:40px 20px 64px}.eyebrow{color:var(--a);font-weight:800;font-size:13px;letter-spacing:.14em;text-transform:uppercase}h1{font-size:40px;line-height:1.1;margin:6px 0 8px}h2{font-size:20px;margin:30px 0 12px}.sub{color:var(--muted);margin:0 0 26px}
.podium{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}.p,.box,details{background:var(--panel);border:1px solid var(--line);border-radius:14px}.p{padding:18px}.p:first-child{border-color:var(--a);box-shadow:0 0 34px #22d3ee33}.rank{color:var(--muted);font:700 13px ui-monospace,monospace}.name{font-size:20px;font-weight:800}.big{font-size:44px;font-weight:900;line-height:1.1}
.d{display:grid;grid-template-columns:118px 1fr 42px;gap:7px;align-items:center;font-size:12px;color:var(--muted);margin:5px 0}.t{height:7px;background:#07131a;border-radius:7px}.f{display:block;height:7px;border-radius:7px;background:linear-gradient(90deg,var(--a),var(--b))}
.box{padding:6px 0;overflow-x:auto}table{width:100%;border-collapse:collapse;min-width:560px}th,td{padding:10px 14px;text-align:left;border-bottom:1px solid #1a333e}tr:last-child td{border:0}th{color:var(--muted);font-size:12px}.c{display:inline-block;min-width:56px;text-align:center;padding:3px 8px;border-radius:7px;font:700 13px ui-monospace,monospace;color:#04161c}.v{font-weight:700}.good{color:var(--b)}.warn{color:var(--warn)}
details{margin:8px 0}summary{padding:12px 16px;cursor:pointer;font-weight:700}.j{padding:0 16px 12px}.j div{padding:6px 0;border-top:1px dashed #1f3b47;font-size:13px;overflow-wrap:anywhere}.j b{color:var(--a)}@media(max-width:640px){h1{font-size:31px}}
"""


def _cell_color(score: float) -> str:
    hue = max(0, min(120, score * 1.2))
    return f"hsl({hue:.0f} 75% 62%)"


def _podium(row: dict, position: int) -> str:
    bars = "".join(
        f'<div class="d"><span>{escape(name.replace("_", " "))}</span><span class="t"><span class="f" style="width:{value:.0f}%"></span></span><span>{value:.0f}</span></div>'
        for name, value in row["dimensions"].items()
    )
    return f'<div class="p"><div class="rank">RANK #{position}</div><div class="name">{escape(row["model"])}</div><div class="big">{row["score"]:.1f}</div>{bars}</div>'


def render_html(results: dict, title: str = "CodeBench Arena") -> str:
    tasks = results["tasks"]
    models = [row["model"] for row in results["leaderboard"]]
    lookup = {(grade["model"], grade["task"]): grade for grade in results["grades"]}
    podium = "".join(_podium(row, index) for index, row in enumerate(results["leaderboard"], 1))
    head = "".join(f"<th>{escape(model)}</th>" for model in models)
    rows = ""
    for task in tasks:
        cells = "".join(
            f'<td><span class="c" style="background:{_cell_color(lookup[(model, task["id"])]["total"])}">{lookup[(model, task["id"])]["total"]:.0f}</span></td>'
            for model in models
        )
        rows += f"<tr><td>{escape(task['title'])}</td>{cells}</tr>"
    calibration = "".join(
        f'<tr><td>{escape(item["task"])}</td><td>{item["mean"]:.1f}</td><td>{item["spread"]:.1f}</td>'
        f'<td class="v {"good" if item["verdict"] == "discriminating" else "warn"}">{escape(item["verdict"])}</td></tr>'
        for item in results["calibration"]
    )
    details = ""
    for model in models:
        for task in tasks:
            grade = lookup[(model, task["id"])]
            lines = "".join(
                f'<div><b>{escape(d["name"])}</b> ({d["score"] * 100:.0f}%, weight {d["weight"]}): {escape(d["justification"])}</div>'
                for d in grade["dimensions"]
            )
            details += f'<details><summary>{escape(model)} · {escape(task["id"])} · {grade["total"]:.1f}</summary><div class="j">{lines}</div></details>'
    return (
        f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title><style>{STYLE}</style><main>'
        f'<div class="eyebrow">LLM coding benchmark</div><h1>{escape(title)}</h1><p class="sub">Hidden tests, static analysis and a written justification for every score.</p>'
        f'<section class="podium">{podium}</section><h2>Score by task</h2><div class="box"><table><tr><th>Task</th>{head}</tr>{rows}</table></div>'
        f'<h2>Task calibration</h2><div class="box"><table><tr><th>Task</th><th>Mean</th><th>Spread</th><th>Verdict</th></tr>{calibration}</table></div>'
        f"<h2>Audit trail</h2>{details}</main></html>"
    )
