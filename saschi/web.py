"""Web workbench: one program, treated at every stage, in a browser.

A single standard-library HTTP server. It serves the static single-page app,
a JSON API over the same job path the CLI uses, the showcase generator, and
an assistant proxy. It binds to 127.0.0.1 by default. No network call leaves
this process unless the operator configured the assistant endpoint, and the
only egress is the assistant turn the operator sends.

The API is JSON-first for the same reason the CLI is: the workbench renders
artifacts, it does not make them. Every stage on screen is the artifact the
run command would have written.
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .assistant import (AssistantError, AssistantNotConfigured, assistant_context,
                        chat, hermes_config)
from .job import build_job
from .provenance import environment
from .showcase import build_showcase

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / 'web' / 'static'
STATIC_NAMES = {'index.html': 'text/html; charset=utf-8',
                'style.css': 'text/css; charset=utf-8',
                'app.js': 'text/javascript; charset=utf-8'}

# Demo programs shipped with the repository. Each names its inputs and
# expected output siblings when the workflow needs them.
PROGRAMS = [
    {'path': 'examples/pgm/rounding_program.sas',
     'name': 'rounding program',
     'note': 'ROUND half-away-from-zero across half-unit boundaries',
     'inputs': None, 'expect': None},
    {'path': 'examples/workflow/job.sas',
     'name': 'workflow',
     'note': 'round, sort, and a one-to-many MERGE',
     'inputs': 'examples/workflow/inputs.json',
     'expect': 'examples/workflow/expected.json'},
    {'path': 'examples/events/job.sas',
     'name': 'data events',
     'note': 'OUTPUT snapshots, WHERE, and BY-group flags',
     'inputs': 'examples/events/inputs.json',
     'expect': 'examples/events/expected.json'},
]


def resolve_program(root: Path, rel: str) -> Path:
    """Resolve a repository-relative path and refuse anything outside the tree."""
    candidate = (root / rel).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ValueError(f'path escapes the repository: {rel}')
    if not candidate.is_file():
        raise ValueError(f'no such file: {rel}')
    return candidate


def program_job(root: Path, spec: dict) -> dict:
    """Run one program from a spec: either a repo path or pasted source."""
    inputs = expect = None
    source_text = None
    if spec.get('path'):
        path = resolve_program(root, spec['path'])
        demo = next((p for p in PROGRAMS if p['path'] == spec['path']), None)
        source_text = path.read_text(encoding='utf-8')
        if demo:
            inputs = resolve_program(root, demo['inputs']) if demo['inputs'] else None
            expect = resolve_program(root, demo['expect']) if demo['expect'] else None
    elif spec.get('source'):
        source_text = spec['source']
    else:
        raise ValueError('provide path or source')
    job = build_job(source_text, inputs, expect, spec.get('target', 'python'))
    return {'accepted': job.receipt['accepted'], 'code': job.code,
            'source': job.source, 'source_sha256': job.source_sha256, 'plan': job.plan.to_dict(),
            'translation': {'code': job.translation.code, 'blocked': job.translation.blocked,
                            'tickets': [vars(t) for t in job.translation.tickets]},
            'result': job.result, 'receipt': job.receipt,
            'showcase': build_showcase(job, spec.get('name') or 'program')}


class WorkbenchHandler(BaseHTTPRequestHandler):
    root = ROOT

    def log_message(self, format, *args):
        pass

    def _send(self, status: int, body: bytes, content_type: str, extra: "dict | None" = None):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, value: dict):
        self._send(status, json.dumps(value, allow_nan=False).encode('utf-8'), 'application/json')

    def _api_error(self, status: int, message: str):
        self._json(status, {'error': message})

    def do_GET(self):
        try:
            self._get()
        except ValueError as exc:
            self._api_error(400, str(exc))
        except Exception as exc:
            self._api_error(500, f'{type(exc).__name__}: {exc}')

    def _get(self):
        parsed = urlparse(self.path)
        parts = parsed.path.strip('/')
        if parts == '' or parts == 'index.html':
            self._send(200, (STATIC_DIR / 'index.html').read_bytes(),
                       STATIC_NAMES['index.html'])
            return
        if parts.startswith('static/'):
            name = parts[len('static/'):]
            if name in STATIC_NAMES:
                self._send(200, (STATIC_DIR / name).read_bytes(), STATIC_NAMES[name])
                return
            self._api_error(404, f'no such static file: {name}')
            return
        if parts == 'api/health':
            info = environment()
            self._json(200, {'ok': True, 'version': __version__,
                             'assistant_configured': hermes_config() is not None,
                             'environment': info})
            return
        if parts == 'api/programs':
            self._json(200, {'programs': PROGRAMS})
            return
        if parts == 'api/program':
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            self._json(200, program_job(self.root, query))
            return
        if parts == 'api/showcase':
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            if not query.get('path'):
                self._api_error(400, 'showcase needs path')
                return
            demo = next((p for p in PROGRAMS if p['path'] == query['path']), None)
            job = program_job(self.root, query)
            extra = {'Content-Disposition': 'attachment; filename="saschi-showcase.html"'} \
                if query.get('download') == '1' else None
            self._send(200, job['showcase'].encode('utf-8'), 'text/html; charset=utf-8', extra)
            return
        self._api_error(404, 'no such route')

    def do_POST(self):
        try:
            self._post()
        except ValueError as exc:
            self._api_error(400, str(exc))
        except Exception as exc:
            self._api_error(500, f'{type(exc).__name__}: {exc}')

    def _post(self):
        parsed = urlparse(self.path)
        if parsed.path != '/api/program' and parsed.path != '/api/chat':
            self._api_error(404, 'no such route')
            return
        length = int(self.headers.get('Content-Length') or 0)
        if length <= 0 or length > 5_000_000:
            self._api_error(400, 'empty body or body over 5 MB')
            return
        try:
            spec = json.loads(self.rfile.read(length).decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._api_error(400, f'body is not JSON: {exc}')
            return
        if not isinstance(spec, dict):
            self._api_error(400, 'body must be a JSON object')
            return
        if parsed.path == '/api/program':
            self._json(200, program_job(self.root, spec))
            return
        self._chat(spec)

    def _chat(self, spec: dict):
        message = spec.get('message')
        if not isinstance(message, str) or not message.strip():
            self._api_error(400, 'message must be a non-empty string')
            return
        context = spec.get('context')
        if context is not None and not isinstance(context, str):
            self._api_error(400, 'context must be a string when present')
            return
        if hermes_config() is None:
            self._json(200, {'configured': False, 'reply': None,
                             'note': 'assistant off: set SASCHI_HERMES_URL and '
                                     'SASCHI_HERMES_API_KEY in the server environment'})
            return
        messages = assistant_context(context) + [{'role': 'user', 'content': message}]
        try:
            result = chat(messages)
        except AssistantNotConfigured:
            self._json(200, {'configured': False, 'reply': None, 'note': 'assistant off'})
            return
        except AssistantError as exc:
            self._api_error(502, f'assistant call failed: {exc}')
            return
        self._json(200, {'configured': True, **result})


def make_server(host: str = '127.0.0.1', port: int = 8070, root: "Path | None" = None) -> ThreadingHTTPServer:
    handler = type('BoundWorkbenchHandler', (WorkbenchHandler,), {'root': root or ROOT})
    return ThreadingHTTPServer((host, port), handler)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog='saschi serve',
                                     description='run the web workbench (stdlib only)')
    parser.add_argument('--host', default='127.0.0.1',
                        help='bind address (default 127.0.0.1; use the tailnet IP to share)')
    parser.add_argument('--port', type=int, default=8070)
    parser.add_argument('--root', type=Path, default=ROOT,
                        help='repository root the program shelf reads from')
    args = parser.parse_args(argv)
    server = make_server(args.host, args.port, args.root)
    print(json.dumps({'listening': f'http://{args.host}:{args.port}/',
                      'assistant': 'configured' if hermes_config() else 'off'}))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
