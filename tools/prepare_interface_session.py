#!/usr/bin/env python3
"""Prepare a local, first-party human session without inventing observations."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from saschi.job import build_job
from saschi.provenance import source_state
from saschi.showcase import build_showcase

TASKS = [
    ('shelf', 'Find a program', 'Open the workbench. Choose a shelf program and explain what Run treatment will do.',
     None, 'Can the operator locate the source and describe the operation?'),
    ('uncompared', 'Read a successful run', 'Run the date program. Explain which checks occurred and what ACCEPTED means here.',
     'date_profile', 'Execution succeeds. Dataset and report comparisons are not requested. R availability is separate from job evidence.'),
    ('evidence', 'Compare two documents', 'Open documents A and B. Describe what evidence differs between them.',
     None, 'A has no requested comparison. B has matching dataset and report expectations. Neither has a per-job R or SAS comparison.'),
    ('pictures', 'Find a formatted result', 'Run the integer-picture program. Find and explain the 09/99 output difference.',
     'numeric_pictures', 'The Run stage shows complete logical report text before stored datasets.'),
    ('callbacks', 'Read a date window', 'Run the week program. Explain the blank repeated customer cells and the date window.',
     'week_callbacks', 'Repeated observations remain. ORDER display suppresses repeated customer text; date callbacks determine the window.'),
    ('refusal', 'Understand a refusal', 'Run the date program with weekdate37 changed to weekdate50. Explain the outcome.',
     'date_profile', 'The current job is blocked. Its ticket explains the unsupported width. A previous success is not current evidence.'),
    ('recover', 'Recover', 'Restore weekdate37 and run again. Locate the new job and its evidence state.',
     'date_profile', 'The current valid job is accepted with comparisons not requested.'),
    ('title', 'Check a fresh job', 'Run the date program after removing its TITLE statements. Inspect the output title.',
     'date_profile', 'A previous job title must not appear in the fresh job.'),
    ('keyboard', 'Keyboard and zoom', 'Use only the keyboard to choose a program, run it, change stages, and read output. Then increase browser zoom.',
     None, 'Record focus loss, clipped content, inaccessible controls, or confusing reading order. Automated checks do not establish usability.'),
]


def prepare(destination):
    destination.mkdir(parents=True, exist_ok=True)
    source = (ROOT / 'examples/date_profile.sas').read_text()
    expected = json.loads((ROOT / 'examples/date_profile_expected.json').read_text())
    with tempfile.TemporaryDirectory(prefix='saschi-interface-') as temporary:
        area = Path(temporary)
        datasets, reports = area / 'datasets.json', area / 'reports.json'
        datasets.write_text(json.dumps(expected['datasets']))
        reports.write_text(json.dumps(expected['reports']))
        jobs = [('a.html', build_job(source)),
                ('b.html', build_job(source, expect=datasets, expect_reports=reports))]
    for name, job in jobs:
        if not job.receipt['accepted']:
            raise ValueError('interface preparation job failed; no session prepared')
        (destination / name).write_text(build_showcase(job, 'Date evidence ' + name[0].upper()))
    binding = source_state(ROOT)
    panels = []
    for key, title, prompt, fixture, check in TASKS:
        sources = ''
        if fixture:
            text = (ROOT / 'examples' / (fixture + '.sas')).read_text()
            if key == 'refusal':
                text = text.replace('weekdate37', 'weekdate50')
            elif key == 'title':
                text = '\n'.join(line for line in text.splitlines() if not line.lower().startswith('title')) + '\n'
            sources = (f'<details><summary>Program for this task</summary>'
                       f'<label for="source-{key}">Source to paste in the workbench</label>'
                       f'<textarea readonly id="source-{key}">{html.escape(text)}</textarea>'
                       f'<button type="button" data-copy="source-{key}">Copy source</button></details>')
        links = '<p><a href="a.html" target="_blank">Document A</a> · <a href="b.html" target="_blank">Document B</a></p>' if key == 'evidence' else ''
        panels.append(f'''<section data-task="{key}">
<h2>{len(panels)+1}. {html.escape(title)}</h2><p>{html.escape(prompt)}</p>{links}{sources}
<label for="outcome-{key}">Outcome</label>
<select id="outcome-{key}"><option value="unattempted">Not attempted</option><option>Completed without help</option><option>Completed with help</option><option>Not completed</option></select>
<label for="notes-{key}">Your interpretation and any blocking point</label>
<textarea id="notes-{key}" placeholder="Record what you thought happened before opening the facilitator check."></textarea>
<details class="check"><summary>Facilitator check, open after recording</summary><p>{html.escape(check)}</p></details>
</section>''')
    document = TEMPLATE.replace('@@PANELS@@', '\n'.join(panels)).replace('@@BINDING@@',
        json.dumps({'commit': binding['git_commit'], 'source_sha256': binding['source_sha256']}))
    (destination / 'index.html').write_text(document)
    manifest = {'status': 'Prepared first-party human session for principal use. Completed human sessions n=0; no usability outcome or native SAS comparison.',
                'source': binding, 'tasks': len(TASKS), 'human_sessions': 0,
                'files': {name: hashlib.sha256((destination/name).read_bytes()).hexdigest()
                          for name in ('index.html', 'a.html', 'b.html')}}
    (destination / 'preparation.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return destination / 'index.html'


TEMPLATE = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SASchi-Go | Morning test drive</title><style>
:root { color-scheme: dark; font-family: system-ui, sans-serif; background: #0d1117; color: #e6edf3; }
body { max-width: 900px; margin: auto; padding: 28px 20px 80px; line-height: 1.6; }
h1 { font-size: clamp(28px, 5vw, 44px); margin-bottom: 0; } h2 { font-size: 21px; }
section { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; margin: 22px 0; }
.eyebrow { color: #7ee787; text-transform: uppercase; letter-spacing: .12em; font-size: 12px; }
a, summary { color: #79c0ff; } label { display: block; margin-top: 14px; }
textarea, select { box-sizing: border-box; width: 100%; background: #0d1117; color: #e6edf3; border: 1px solid #484f58; border-radius: 6px; padding: 10px; font: inherit; }
textarea { min-height: 90px; resize: vertical; } textarea[readonly] { height: 240px; font: 12px/1.5 monospace; }
button { padding: 10px 16px; margin-top: 12px; background: #238636; border: 1px solid #3fb950; border-radius: 6px; color: white; cursor: pointer; }
:focus-visible { outline: 3px solid #79c0ff; outline-offset: 3px; } summary { cursor: pointer; }
.muted, .check { color: #b1bac4; font-size: 14px; } .check { margin-top: 20px; }
#binding { overflow-wrap: anywhere; } .toolbar { position: sticky; bottom: 0; background: #0d1117; border-top: 1px solid #30363d; padding: 12px 0; }
</style></head><body>
<p class="eyebrow">SASchi-Go / human session</p><h1>Morning test drive</h1>
<p>Nine short tasks. Bring coffee and your most suspicious eyebrow.</p>
<p class="muted">Status: staged human protocol for the principal or another operator. Completed human sessions n=0 at preparation. Automated results are separate; this page makes no usability or native SAS claim.</p>
<p><a href="http://127.0.0.1:8070" target="_blank">Open the local workbench</a>. If it is closed, start it from the repository with <code>.venv/bin/python -m saschi serve</code>.</p>
<p>Record your interpretation first. The facilitator checks contain answers. Notes stay in this page until you explicitly export them; reload clears them. Keep personal information out of notes.</p>
<p class="muted" id="binding"></p>
<label for="surface">Browser, zoom, window size and input method (optional)</label><input id="surface" type="text">
@@PANELS@@
<div class="toolbar"><span id="progress" role="status">0 of 9 tasks attempted</span><br><button id="export" type="button">Export my observations</button><span id="notice" role="status"></span></div>
<script>
'use strict';
const binding = @@BINDING@@;
document.getElementById('binding').textContent = 'Prepared from commit ' + binding.commit + ', working-source digest ' + binding.source_sha256 + '. Match this to the verification receipt before testing.';
const sections = [...document.querySelectorAll('section[data-task]')];
function observations() { return sections.map(s => { const id = s.dataset.task; return {task: id, outcome: document.getElementById('outcome-'+id).value, observation: document.getElementById('notes-'+id).value}; }); }
document.addEventListener('change', () => { document.getElementById('progress').textContent = observations().filter(x => x.outcome !== 'unattempted').length + ' of 9 tasks attempted'; });
document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {
 const field = document.getElementById(button.dataset.copy);
 try { await navigator.clipboard.writeText(field.value); button.textContent = 'Copied'; }
 catch (_) { field.focus(); field.select(); button.textContent = 'Source selected; copy with your keyboard'; }
}));
document.getElementById('export').addEventListener('click', () => {
 const rows = observations();
 const result = {status: 'Operator-entered observations for maintainer review; not independently verified and not a population usability estimate.', prepared_source: binding, recorded_at: new Date().toISOString(), surface: document.getElementById('surface').value, attempted_tasks: rows.filter(x => x.outcome !== 'unattempted').length, observations: rows};
 const url = URL.createObjectURL(new Blob([JSON.stringify(result,null,2)+'\\n'], {type:'application/json'}));
 const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'saschi-human-observations.json'; anchor.click();
 setTimeout(() => URL.revokeObjectURL(url), 1000);
 document.getElementById('notice').textContent = ' Export prepared. No observations were sent to a server.';
});
</script></body></html>'''


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(prepare(args.output.resolve()))
