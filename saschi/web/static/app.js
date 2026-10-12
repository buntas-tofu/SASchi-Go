"use strict";

const $ = (id) => document.getElementById(id);
let currentJob = null;
let activeTab = 'plan';

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} returned ${res.status}`);
  return res.json();
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `${url} returned ${res.status}`);
  return data;
}

const esc = (s) => String(s == null ? '' : s)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function valueText(v) {
  if (v === null) return '[missing]';
  if (typeof v === 'object') return '[missing:' + (v.missing || '?') + ']';
  if (typeof v === 'string') return '"' + v + '"';
  if (typeof v === 'number' && Number.isFinite(v)) return v.toPrecision(17).replace(/0+$/, '').replace(/\.$/, '');
  return String(v);
}

function dataTable(table) {
  const schema = table.schema || {};
  const rows = table.rows || [];
  const cols = Object.keys(schema);
  const shown = rows.slice(0, 200);
  let html = '<table><thead><tr>' + cols.map((c) => `<th>${esc(c)}</th>`).join('') + '</tr></thead><tbody>';
  for (const row of shown) {
    html += '<tr>' + cols.map((c) => `<td class="mono">${esc(valueText(row[c]))}</td>`).join('') + '</tr>';
  }
  html += '</tbody></table>';
  if (rows.length > 200) html += `<p class="meta">${rows.length - 200} more rows, not shown.</p>`;
  return html;
}

function renderStages(job) {
  const tabs = [
    ['source', 'Source'],
    ['plan', 'Plan' + (job.plan.tickets.length ? '' : '')],
    ['translate', 'Translate'],
    ['run', 'Run'],
    ['compare', 'Compare'],
    ['receipt', 'Receipt']
  ];
  $('tabs').innerHTML = tabs.map(([key, label]) => {
    const n = key === 'plan' ? job.plan.tickets.length : 0;
    return `<span class="tab ${key === activeTab ? 'active' : ''}" data-tab="${key}">${label}${n ? `<span class="n">${n}</span>` : ''}</span>`;
  }).join('');
  for (const el of $('tabs').querySelectorAll('.tab')) {
    el.addEventListener('click', () => { activeTab = el.dataset.tab; renderStages(job); });
  }
  const body = $('stage-body');
  if (activeTab === 'source') {
    body.innerHTML = `<pre class="code">${esc(job.source)}</pre>`;
  } else if (activeTab === 'plan') {
    let html = '';
    for (const step of job.plan.steps) {
      html += `<div class="step-block"><h4>${esc(step.kind)} ${esc(step.name)} <span class="meta">line ${esc(step.line)}</span></h4>`;
      html += `<p class="meta">inputs: <span class="mono">${esc((step.inputs || []).join(', ') || '(none)')}</span> ; by: <span class="mono">${esc((step.by || []).join(', ') || '-')}</span></p>`;
      html += '<table><thead><tr><th>line</th><th>kind</th><th>args</th></tr></thead><tbody>';
      for (const op of (step.operations || [])) {
        html += `<tr><td>${esc(op.line)}</td><td class="mono">${esc(op.kind)}</td><td class="mono">${esc(JSON.stringify(op.args))}</td></tr>`;
      }
      html += '</tbody></table></div>';
    }
    if (job.plan.tickets.length) {
      html += '<h3 style="margin:14px 0 4px">Tickets (these block the artifact)</h3><table><thead><tr><th>line</th><th>construct</th><th>reason</th><th>statement</th></tr></thead><tbody>';
      for (const t of job.plan.tickets) {
        html += `<tr class="ticket-row"><td>${esc(t.line)}</td><td class="mono">${esc(t.construct)}</td><td>${esc(t.reason)}</td><td class="mono">${esc(t.statement)}</td></tr>`;
      }
      html += '</tbody></table>';
    } else {
      html += '<p class="meta">no tickets; every statement routed to a gated construct</p>';
    }
    body.innerHTML = html || '<p class="notreached">no steps parsed</p>';
  } else if (activeTab === 'translate') {
    const t = job.translation;
    body.innerHTML = (t.blocked
      ? '<p class="notreached">translation blocked; the code shown is an inspection artifact, not an executable.</p>'
      : '') + (t.code ? `<pre class="code">${esc(t.code)}</pre>` : '<p class="notreached">no translation produced</p>');
  } else if (activeTab === 'run') {
    if (job.result) {
      let html = '';
      for (const [name, table] of Object.entries(job.result.datasets || {})) {
        html += `<h3 style="margin:12px 0 4px">${esc(name)}</h3>${dataTable(table)}`;
      }
      if (job.result.log && job.result.log.length) {
        html += '<h3 style="margin:12px 0 4px">log</h3><pre class="code">' + esc(job.result.log.join('\n')) + '</pre>';
      }
      body.innerHTML = html;
    } else {
      body.innerHTML = `<p class="notreached">not reached: ${esc(job.receipt.error || 'no execution was performed')}</p>`;
    }
  } else if (activeTab === 'compare') {
    const c = job.receipt.comparison || 'not requested';
    if (c === 'passed') body.innerHTML = '<p class="meta">passed: the typed exact-values contract held over the expected datasets.</p>';
    else if (c === 'failed') body.innerHTML = `<p style="color:#f85149">failed: ${esc(job.receipt.error || 'expected dataset differs')}</p>`;
    else body.innerHTML = '<p class="meta">not requested for this run.</p>';
  } else {
    body.innerHTML = '<details open><summary>receipt.json</summary><pre class="code">' +
      esc(JSON.stringify(job.receipt, null, 2)) + '</pre></details>';
  }
}

function renderJob(job, name) {
  currentJob = job;
  const blocked = job.plan.tickets.length > 0;
  const verdict = $('verdict');
  if (job.accepted) { verdict.className = 'ok'; verdict.textContent = 'ACCEPTED'; }
  else if (blocked) { verdict.className = 'fail'; verdict.textContent = 'BLOCKED BY TICKETS'; }
  else { verdict.className = 'warn'; verdict.textContent = 'REJECTED: ' + (job.receipt.error || 'run failed'); }
  $('status-line').textContent =
    `${name} ; source_sha256 ${job.source_sha256} ; ${job.receipt.environment.python} / ${String(job.receipt.environment.r_version || 'no R').slice(0, 40)}`;
  renderStages(job);
  const ctx = job.receipt.comparison === 'passed'
    ? 'comparison passed' : 'comparison: ' + (job.receipt.comparison || 'none');
  $('chat-context').textContent = `context attached: ${name}, ${job.plan.tickets.length} tickets, ${ctx}`;
}

function jobContext() {
  if (!currentJob) return null;
  const tickets = currentJob.plan.tickets.map(
    (t) => `line ${t.line}: ${t.construct} -> ${t.reason} ("${t.statement}")`).join('\n');
  return `program:\n${currentJob.source}\n\ntickets:\n${tickets || 'none'}` +
    `\n\ncomparison: ${currentJob.receipt.comparison}; accepted: ${currentJob.receipt.accepted}`;
}

async function runProgram(spec, name) {
  try {
    const job = await postJSON('/api/program', spec);
    renderJob(job, name);
  } catch (err) {
    const v = $('verdict');
    v.className = 'fail';
    v.textContent = 'ERROR';
    $('status-line').textContent = String(err.message || err);
    $('stage-body').innerHTML = '';
  }
}

function openShowcase(spec, name) {
  postJSON('/api/program', spec).then((job) => {
    const blob = new Blob([job.showcase], { type: 'text/html' });
    window.open(URL.createObjectURL(blob), '_blank');
  }).catch((err) => alert('showcase failed: ' + err));
}

async function init() {
  try {
    const health = await getJSON('/api/health');
    $('version').textContent = 'v' + health.version;
    const env = health.environment;
    $('env').textContent =
      `${env.host} ; python ${env.python} ; ${String(env.r_version || 'no R').slice(0, 24)} ; ${env.cpp_version || 'no C++17'}`;
  } catch (err) {
    $('env').textContent = 'health check failed: ' + err;
  }
  const chatStatus = $('chat-status');
  try {
    const health = await getJSON('/api/health');
    chatStatus.textContent = health.assistant_configured
      ? 'assistant: on (Hermes endpoint)'
      : 'assistant: off. set SASCHI_HERMES_URL and SASCHI_HERMES_API_KEY to enable.';
  } catch (err) { chatStatus.textContent = 'assistant: unknown'; }

  const list = $('program-list');
  try {
    const data = await getJSON('/api/programs');
    for (const p of data.programs) {
      const el = document.createElement('div');
      el.className = 'program';
      el.innerHTML = `<div class="name">${esc(p.name)}</div><div class="note">${esc(p.note)}</div>`;
      el.addEventListener('click', () => {
        for (const other of list.children) other.classList.remove('active');
        el.classList.add('active');
        activeTab = 'plan';
        runProgram({ path: p.path }, p.name);
      });
      list.appendChild(el);
    }
  } catch (err) {
    list.innerHTML = `<p class="meta">program shelf unavailable: ${esc(err)}</p>`;
  }

  $('run-paste').addEventListener('click', () => {
    const source = $('paste').value.trim();
    if (!source) return;
    activeTab = 'plan';
    runProgram({ source }, 'pasted program');
  });

  $('chat-send').addEventListener('click', async () => {
    const input = $('chat-input');
    const message = input.value.trim();
    if (!message) return;
    const log = $('chat-log');
    const userMsg = document.createElement('div');
    userMsg.className = 'msg user';
    userMsg.textContent = message;
    log.appendChild(userMsg);
    input.value = '';
    $('chat-send').disabled = true;
    try {
      const data = await postJSON('/api/chat', { message, context: jobContext() });
      if (!data.configured) {
        const note = document.createElement('div');
        note.className = 'msg';
        note.textContent = data.note;
        log.appendChild(note);
        return;
      }
      const reply = document.createElement('div');
      reply.className = 'msg reply';
      reply.innerHTML = esc(data.reply) +
        `<span class="advisory-tag">${esc(data.status_line || 'assistant output; not a verified translation')}</span>`;
      log.appendChild(reply);
    } catch (err) {
      const errEl = document.createElement('div');
      errEl.className = 'msg';
      errEl.textContent = 'assistant error: ' + err;
      log.appendChild(errEl);
    } finally {
      $('chat-send').disabled = false;
      log.scrollTop = log.scrollHeight;
    }
  });
}

init();
