"""Render a job as a single self-contained showcase document.

The showcase is the output, not the app: one HTML file, no external assets,
that details the treatment of one program at every stage, source to receipt.
It renders only artifacts the job actually produced. A stage the job did not
reach is labeled not reached, never filled in.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from . import __version__
from .job import Job

MAX_ROWS = 500

STAGES = [
    ('source', '1. Source'),
    ('plan', '2. Parse and route'),
    ('translate', '3. Translate'),
    ('run', '4. Execute'),
    ('compare', '5. Compare'),
    ('receipt', '6. Receipt'),
]


def _value(v) -> str:
    if v is None:
        return '[missing]'
    if isinstance(v, dict):
        return '[missing:' + str(v.get('missing', '?')) + ']'
    if isinstance(v, str):
        return '"' + str(v) + '"'
    if isinstance(v, float):
        return format(v, '.17g')
    return str(v)


def _table(table: dict, cap: int = MAX_ROWS) -> str:
    schema = table.get('schema', {})
    rows = table.get('rows', [])
    shown, note = rows[:cap], ''
    if len(rows) > cap:
        note = f'<p class="note">{len(rows) - cap} more rows, not shown.</p>'
    head = ''.join(f'<th>{html.escape(name)}</th>' for name in schema)
    body = []
    for row in shown:
        body.append('<tr>' + ''.join(f'<td>{html.escape(_value(row.get(name)))}</td>' for name in schema) + '</tr>')
    return (f'<table class="data"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>{note}')


def _step_block(step: dict) -> str:
    inputs = ' '.join(step.get('inputs', [])) or '(none)'
    by = ' '.join(step.get('by', [])) or '-'
    ops = []
    for op in step.get('operations', []):
        ops.append(f"<tr><td>{html.escape(str(op.get('line', '')))}</td>"
                   f"<td class='mono'>{html.escape(op.get('kind', ''))}</td>"
                   f"<td class='mono'>{html.escape(json.dumps(op.get('args', {}), sort_keys=True))}</td></tr>")
    return (f"<section class='step'><h4>{html.escape(step.get('kind', '?'))} "
            f"{html.escape(step.get('name', '?'))} <span class='dim'>line {step.get('line', '?')}</span></h4>"
            f"<p class='meta'>inputs: <span class='mono'>{html.escape(inputs)}</span> ; "
            f"by: <span class='mono'>{html.escape(by)}</span></p>"
            f"<table class='ops'><thead><tr><th>line</th><th>kind</th><th>args</th></tr></thead>"
            f"<tbody>{''.join(ops) or '<tr><td colspan=3>no operations</td></tr>'}</tbody></table></section>")


def build_showcase(job: Job, name: str, source_label: str = "pasted program") -> str:
    plan = job.plan.to_dict()
    receipt = job.receipt
    blocked = bool(plan['tickets'])
    verdict = receipt.get('accepted', False)

    tickets = []
    for t in plan['tickets']:
        tickets.append(f"<tr><td>{html.escape(str(t.get('line', '')))}</td>"
                       f"<td class='mono'>{html.escape(t.get('construct', ''))}</td>"
                       f"<td>{html.escape(t.get('reason', ''))}</td>"
                       f"<td class='mono'>{html.escape(t.get('statement', ''))}</td></tr>")

    if job.result is not None:
        datasets = []
        for dname, table in job.result.get('datasets', {}).items():
            datasets.append(f"<h4>{html.escape(dname)}</h4>{_table(table)}")
        logs = job.result.get('log', [])
        log_html = ('<pre class="mono">' + html.escape('\n'.join(logs)) + '</pre>') if logs else "<p class='dim'>no log lines</p>"
        run_html = ''.join(f"<section class='step'>{d}</section>" for d in datasets) + log_html
    else:
        run_html = _not_reached(receipt)

    comparison = receipt.get('comparison', 'not requested')
    if comparison in ('passed', 'failed'):
        badge = 'ok' if comparison == 'passed' else 'fail'
        compare_html = (f"<p class='verdict {badge}'>comparison {comparison}: the typed exact-values contract "
                        f"{'held' if comparison == 'passed' else 'broke'} over the expected datasets.</p>"
                        f"<p class='meta'>expected_sha256 <span class='mono'>{html.escape(receipt.get('expected_sha256', ''))}</span></p>")
    else:
        compare_html = "<p class='dim'>Not requested for this run.</p>"

    translation_code = job.translation.code if job.translation else ''
    trans_note = ''
    if job.translation and job.translation.blocked:
        trans_note = "<p class='verdict fail'>translation blocked; the code shown is an inspection artifact, not an executable.</p>"
    elif not translation_code:
        trans_note = "<p class='dim'>No translation produced.</p>"

    source_html = '<pre class="mono">' + html.escape(job.source) + '</pre>'

    env = receipt.get('environment', {})
    header_meta = (f"host <span class='mono'>{html.escape(str(env.get('host', '?')))}</span> ; "
                   f"python <span class='mono'>{html.escape(str(env.get('python', '?')))}</span> ; "
                   f"R <span class='mono'>{html.escape(str(env.get('r_version', 'absent'))[:60])}</span> ; "
                   f"tool <span class='mono'>{__version__}</span>")

    badge = 'ok' if verdict else ('fail' if blocked else 'warn')
    badge_text = 'ACCEPTED' if verdict else ('BLOCKED' if blocked else 'REJECTED')
    status_line = (f"Status: verified fixture evidence at the rungs shown below; "
                   f"{'Python and R agree with the documented rule' if verdict else 'the job did not complete acceptance'}. "
                   f"No live SAS. What would change it: a different tool commit, environment, or input.")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SASchi-Go showcase: {html.escape(name)}</title>
<style>
:root {{ color-scheme: dark; }}
body {{ margin: 0; background: #0d1117; color: #e6edf3; font: 15px/1.55 system-ui, sans-serif; }}
.wrap {{ max-width: 980px; margin: 0 auto; padding: 32px 24px 64px; }}
header h1 {{ font-size: 24px; margin: 0 0 4px; }}
header .dim {{ color: #8b949e; font-size: 13px; }}
.verdict {{ font-weight: 600; padding: 10px 14px; border-radius: 6px; }}
.verdict.ok {{ background: #12351c; color: #56d364; border: 1px solid #1f6f38; }}
.verdict.fail {{ background: #3d1214; color: #f85149; border: 1px solid #8e2b2f; }}
.verdict.warn {{ background: #3a2d0e; color: #e3b341; border: 1px solid #7a5f1d; }}
.status {{ color: #8b949e; font-size: 13px; margin: 14px 0 28px; }}
.stage {{ border: 1px solid #21262d; border-radius: 8px; padding: 18px 20px; margin: 18px 0; }}
.stage h2 {{ font-size: 16px; margin: 0 0 12px; color: #e6edf3; }}
.stage h4 {{ margin: 14px 0 6px; }}
.dim {{ color: #8b949e; }}
.meta {{ color: #8b949e; font-size: 13px; }}
.mono, pre.mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; }}
pre.mono {{ background: #161b22; border: 1px solid #21262d; border-radius: 6px; padding: 12px; overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
th, td {{ border: 1px solid #21262d; padding: 5px 8px; text-align: left; }}
th {{ background: #161b22; font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; }}
table.data td {{ font-family: ui-monospace, monospace; font-size: 13px; }}
tr.ticket td {{ background: #3d1214; }}
.step {{ margin: 12px 0; padding-left: 12px; border-left: 2px solid #21262d; }}
.note {{ color: #8b949e; font-size: 13px; }}
details summary {{ cursor: pointer; color: #79c0ff; }}
footer {{ margin-top: 32px; color: #8b949e; font-size: 12px; }}
</style>
</head>
<body>
<div class="wrap">
<header>
<h1>SASchi-Go showcase: {html.escape(name)}</h1>
<div class="dim">{html.escape(source_label)} ; source_sha256 <span class="mono">{html.escape(job.source_sha256)}</span> ;
generated {html.escape(datetime.now(timezone.utc).isoformat(timespec='seconds'))}</div>
</header>
<p class="verdict {badge}">{badge_text}</p>
<p class="status">{status_line} {header_meta}</p>

<section class="stage" id="stage-source">
<h2>1. Source</h2>
{source_html}
</section>

<section class="stage" id="stage-plan">
<h2>2. Parse and route</h2>
<p class="meta">Every statement is routed through the rulebook. A statement the translator cannot fully
account for becomes a ticket, and a ticket blocks the artifact. Tickets are shown highlighted.</p>
{''.join(_step_block(s) for s in plan['steps']) or "<p class='dim'>no steps parsed</p>"}
{'<h4>Tickets</h4><table class="ops"><thead><tr><th>line</th><th>construct</th><th>reason</th><th>statement</th></tr></thead><tbody>' + ''.join(tickets) + '</tbody></table>' if tickets else '<p class="dim">no tickets; every statement routed to a gated construct</p>'}
</section>

<section class="stage" id="stage-translate">
<h2>3. Translate</h2>
{trans_note}
{('<pre class="mono">' + html.escape(translation_code) + '</pre>') if translation_code else ''}
</section>

<section class="stage" id="stage-run">
<h2>4. Execute</h2>
{run_html}
</section>

<section class="stage" id="stage-compare">
<h2>5. Compare</h2>
{compare_html}
</section>

<section class="stage" id="stage-receipt">
<h2>6. Receipt</h2>
<p class="meta">The checksummed machine artifact for this job. The document above is a rendering of it;
the JSON is the record.</p>
<details><summary>receipt.json</summary>
<pre class="mono">{html.escape(json.dumps(receipt, indent=2, allow_nan=False))}</pre>
</details>
</section>

<footer>SASchi-Go {__version__} ; generated by saschi showcase ; single-file document, no external assets.</footer>
</div>
</body>
</html>
"""


def _not_reached(receipt: dict) -> str:
    reason = html.escape(receipt.get('error', 'no execution was performed'))
    return f"<p class='dim'>Not reached: {reason}</p>"
