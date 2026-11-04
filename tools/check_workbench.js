#!/usr/bin/env node
'use strict';
// Supplemental isolated JavaScript checks. No browser, network, or production
// dependency; these do not establish layout, focus behavior, or human usability.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const filename = path.join(__dirname, '..', 'saschi', 'web', 'static', 'app.js');
const source = fs.readFileSync(filename, 'utf8');
assert.match(source, /\ninit\(\);\s*$/);
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {innerHTML: '', textContent: '', className: '',
    querySelectorAll: () => []});
  return elements.get(id);
}
const requests = [];
const context = vm.createContext({
  document: {getElementById: element},
  fetch: () => new Promise((resolve, reject) => requests.push({resolve, reject})),
});
// Suppress boot-time I/O, then execute the actual shipped renderer functions.
vm.runInContext(source.replace(/\ninit\(\);\s*$/, '\n'), context, {filename});
const evaluate = code => vm.runInContext(code, context);
let checks = 0;
function check(name, action) {
  action(); checks++;
  console.log(JSON.stringify({case: name, passed: true}));
}

function job(label) {
  return {accepted: true, source: label, source_sha256: 'test-hash',
    plan: {steps: [], tickets: []}, translation: {code: '', blocked: false},
    result: {datasets: {}, reports: {'report_01.txt': '<unsafe>\n09 99\n'}, log: []},
    receipt: {accepted: true, comparison: 'not requested', report_comparison: 'passed',
      environment: {python: 'test', r_version: 'available'}}};
}

async function main() {
  check('numeric-text-preserves-extreme-exponents', () => {
    for (const value of [1e20, 1e-10, 1e30, 1e100, -1e-100, Number.MAX_VALUE,
      Number.MIN_VALUE, 0, 42, 1.25, 0.30000000000000004]) {
      context.value = value;
      assert.equal(Number(evaluate('valueText(value)')), value);
    }
  });
  check('numeric-text-4096-seeded-binary64-values', () => {
    let state = 20261103;
    const next = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return state; };
    const buffer = new ArrayBuffer(8), view = new DataView(buffer);
    let finite = 0;
    while (finite < 4096) {
      view.setUint32(0, next()); view.setUint32(4, next());
      const value = view.getFloat64(0);
      if (!Number.isFinite(value)) continue;
      context.value = value;
      assert.equal(Number(evaluate('valueText(value)')), value);
      finite++;
    }
  });
  context.job = job('report');
  check('run-stage-renders-escaped-complete-report', () => {
    evaluate("activeTab = 'run'; renderStages(job)");
    assert.match(element('stage-body').innerHTML, /report_01\.txt/);
    assert.match(element('stage-body').innerHTML, /&lt;unsafe&gt;\n09 99\n/);
    assert.doesNotMatch(element('stage-body').innerHTML, /<unsafe>/);
  });
  check('compare-stage-separates-report-and-dataset-evidence', () => {
    evaluate("activeTab = 'compare'; renderStages(job)");
    assert.match(element('stage-body').innerHTML, /Report comparison: passed/);
    assert.match(element('stage-body').innerHTML, /Dataset comparison: not requested/);
    assert.match(element('stage-body').innerHTML, /No per-job R comparison/);
  });
  check('stage-controls-are-native-buttons', () => {
    assert.equal((element('tabs').innerHTML.match(/<button /g) || []).length, 6);
    assert.match(element('tabs').innerHTML, /aria-pressed="true"/);
  });
  evaluate('renderJob(job, "old job")');
  const earlier = evaluate('runProgram({source: "first"}, "first")');
  check('pending-run-clears-old-evidence-and-assistant-context', () => {
    assert.equal(evaluate('currentJob'), null);
    assert.equal(element('stage-body').innerHTML, '');
    assert.equal(element('tabs').innerHTML, '');
    assert.equal(element('verdict').textContent, 'RUNNING');
  });
  const later = evaluate('runProgram({source: "second"}, "second")');
  requests[1].resolve({ok: true, json: async () => job('second')});
  await later;
  requests[0].resolve({ok: true, json: async () => job('first')});
  await earlier;
  check('late-response-cannot-replace-newer-job', () => {
    assert.equal(evaluate('currentJob.source'), 'second');
    assert.match(element('status-line').textContent, /^second ;/);
  });
  const failing = evaluate('runProgram({source: "failure"}, "failure")');
  requests[2].reject(new Error('test transport failure'));
  await failing;
  check('transport-failure-retains-no-old-evidence', () => {
    assert.equal(evaluate('currentJob'), null);
    assert.equal(evaluate('jobContext()'), null);
    assert.equal(element('stage-body').innerHTML, '');
    assert.equal(element('verdict').textContent, 'ERROR');
  });
  console.log(JSON.stringify({status: 'Isolated JavaScript diagnostics for maintainer review; no browser or human usability claim.', checks, passed: true}));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
