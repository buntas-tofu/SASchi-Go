"""Behavioral tests for the web workbench.

The workbench is a presentation over the job path: these tests pin the
routes, the path boundary (nothing outside the repository), the assistant
off state, and the showcase document served by the server. The server runs
on a loopback port chosen by the kernel; no external network is touched.
"""
import contextlib
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .web import make_server

SMALL = 'data rounded_values;\n  x1 = 0.25;\n  r1 = round(x1, 0.1);\n  put r1=;\nrun;\n'


def get(url):
    with urllib.request.urlopen(url, timeout=30) as res:
        return res.status, res.read().decode('utf-8'), dict(res.headers)


def get_expect_error(url):
    try:
        with urllib.request.urlopen(url, timeout=30) as res:
            return res.status, res.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode('utf-8')


def post(url, payload):
    request = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as res:
        return res.status, json.loads(res.read().decode('utf-8'))


class AssistantOffMixin:
    def clear_assistant_env(self):
        saved = {}
        for name in ('SASCHI_HERMES_URL', 'SASCHI_HERMES_API_KEY', 'SASCHI_HERMES_MODEL'):
            saved[name] = os.environ.pop(name, None)
        return saved

    def restore_assistant_env(self, saved):
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


class WorkbenchTests(AssistantOffMixin, unittest.TestCase):
    def setUp(self):
        self.saved = self.clear_assistant_env()
        self.server = make_server('127.0.0.1', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.restore_assistant_env(self.saved)

    def test_serves_the_app_and_static(self):
        status, body, _ = get(self.base + '/')
        self.assertEqual(status, 200)
        self.assertIn('workbench', body)
        status, body, headers = get(self.base + '/static/style.css')
        self.assertEqual(status, 200)
        self.assertIn('color-scheme', body)
        status, _ = get_expect_error(self.base + '/static/missing.css')
        self.assertEqual(status, 404)

    def test_health_reports_environment_and_assistant_off(self):
        status, body, _ = get(self.base + '/api/health')
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(data['ok'])
        self.assertFalse(data['assistant_configured'])
        self.assertIn('python', data['environment'])

    def test_program_shelf_lists_the_shipped_workflows(self):
        status, body, _ = get(self.base + '/api/programs')
        data = json.loads(body)
        paths = [p['path'] for p in data['programs']]
        self.assertIn('examples/workflow/job.sas', paths)
        self.assertIn('examples/events/job.sas', paths)
        self.assertIn('examples/pgm/rounding_program.sas', paths)

    def test_program_by_path_runs_the_full_treatment(self):
        status, body, _ = get(self.base + '/api/program?path=examples/workflow/job.sas')
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(data['accepted'])
        self.assertIn('data rounded; set raw;', data['source'])
        self.assertIn('joined', data['result']['datasets'])
        self.assertIn('ACCEPTED', data['showcase'])

    def test_program_by_pasted_source_runs(self):
        status, data = post(self.base + '/api/program', {'source': SMALL})
        self.assertEqual(status, 200)
        self.assertTrue(data['accepted'])
        self.assertTrue(data['result']['log'][0].startswith('r1=0.3'))

    def test_blocked_pasted_source_reports_tickets(self):
        status, data = post(self.base + '/api/program',
                            {'source': 'data d;\n  set raw;\n  d = count(x);\nrun;\n'})
        self.assertEqual(status, 200)
        self.assertFalse(data['accepted'])
        self.assertTrue(data['plan']['tickets'])
        self.assertIn('BLOCKED', data['showcase'])

    def test_showcase_serves_the_document(self):
        status, body, headers = get(self.base + '/api/showcase?path=examples/workflow/job.sas')
        self.assertEqual(status, 200)
        self.assertIn('text/html', headers['Content-Type'])
        self.assertIn('SASchi-Go showcase', body)
        status, body, headers = get(self.base + '/api/showcase?path=examples/workflow/job.sas&download=1')
        self.assertIn('attachment', headers.get('Content-Disposition', ''))

    def test_paths_outside_the_repository_are_refused(self):
        status, body = get_expect_error(self.base + '/api/showcase?path=../../etc/passwd')
        self.assertEqual(status, 400)
        status, body = get_expect_error(self.base + '/api/program?path=../../../etc/hostname')
        self.assertEqual(status, 400)

    def test_chat_reports_the_off_state_without_network(self):
        status, data = post(self.base + '/api/chat', {'message': 'what is QTR?'})
        self.assertEqual(status, 200)
        self.assertFalse(data['configured'])
        self.assertIsNone(data['reply'])


class WorkbenchChatTests(AssistantOffMixin, unittest.TestCase):
    """The chat route against a stub Hermes endpoint: the proxy works when configured."""

    def setUp(self):
        class Stub(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def do_POST(self):
                if not self.path.endswith('/chat/completions'):
                    self.send_response(404)
                    self.end_headers()
                    return
                length = int(self.headers.get('Content-Length') or 0)
                body = self.rfile.read(length)
                reply = {'model': 'stub', 'choices': [{'message': {'content': 'advisory only'}}]}
                payload = json.dumps(reply).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.stub = ThreadingHTTPServer(('127.0.0.1', 0), Stub)
        self.stub_thread = threading.Thread(target=self.stub.serve_forever, daemon=True)
        self.stub_thread.start()
        self.saved = self.clear_assistant_env()
        os.environ['SASCHI_HERMES_URL'] = f'http://127.0.0.1:{self.stub.server_address[1]}/v1'
        os.environ['SASCHI_HERMES_API_KEY'] = 'stub-key'
        self.server = make_server('127.0.0.1', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.stub.shutdown()
        self.stub.server_close()
        self.restore_assistant_env(self.saved)

    def test_chat_forwards_and_returns_advisory_reply(self):
        status, body, _ = get(self.base + '/api/health')
        self.assertTrue(json.loads(body)['assistant_configured'])
        status, data = post(self.base + '/api/chat', {'message': 'explain LAG'})
        self.assertEqual(status, 200)
        self.assertTrue(data['configured'])
        self.assertEqual(data['reply'], 'advisory only')
        self.assertTrue(data['advisory'])


if __name__ == '__main__':
    unittest.main()
