"""Behavioral tests for the Hermes adapter.

The assistant is advisory by law and off by default. These tests pin the
off state, the configuration parsing, and the wire behavior against a stub
endpoint that stands in for the operator's Hermes: the bearer header is
sent, the reply comes back advisory, and a failed call surfaces as a
labeled error rather than a silent one.
"""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .assistant import (AssistantError, AssistantNotConfigured, chat,
                        hermes_config)


class StubEndpoint(BaseHTTPRequestHandler):
    last_auth = None
    last_body = None

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        if not self.path.endswith('/chat/completions'):
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get('Content-Length') or 0)
        StubEndpoint.last_auth = self.headers.get('Authorization')
        StubEndpoint.last_body = json.loads(self.rfile.read(length).decode('utf-8'))
        if StubEndpoint.last_body.get('model') == 'explode':
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'boom')
            return
        body = {'model': StubEndpoint.last_body.get('model', 'stub'),
                'choices': [{'message': {'role': 'assistant', 'content': 'stub reply'}}]}
        payload = json.dumps(body).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def run_endpoint():
    server = ThreadingHTTPServer(('127.0.0.1', 0), StubEndpoint)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


class HermesConfigTests(unittest.TestCase):
    def test_off_when_unset(self):
        self.assertIsNone(hermes_config({}))
        self.assertIsNone(hermes_config({'SASCHI_HERMES_URL': 'http://x:1/v1'}))

    def test_on_when_both_set(self):
        config = hermes_config({'SASCHI_HERMES_URL': 'http://x:1/v1/',
                                'SASCHI_HERMES_API_KEY': 'k'})
        self.assertEqual(config['base_url'], 'http://x:1/v1')
        self.assertEqual(config['model'], 'default')


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.server = run_endpoint()
        port = self.server.server_address[1]
        self.config = {'base_url': f'http://127.0.0.1:{port}/v1',
                       'api_key': 'test-key', 'model': 'stub'}

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_chat_returns_advisory_reply(self):
        result = chat([{'role': 'user', 'content': 'what is QTR?'}], self.config)
        self.assertEqual(result['reply'], 'stub reply')
        self.assertTrue(result['advisory'])
        self.assertIn('not a verified translation', result['status_line'])
        self.assertEqual(StubEndpoint.last_auth, 'Bearer test-key')
        self.assertEqual(StubEndpoint.last_body['messages'][-1]['content'], 'what is QTR?')

    def test_failed_call_raises_labeled_error(self):
        bad = dict(self.config, model='explode')
        with self.assertRaises(AssistantError):
            chat([{'role': 'user', 'content': 'x'}], bad)

    def test_unconfigured_call_raises(self):
        with self.assertRaises(AssistantNotConfigured):
            chat([{'role': 'user', 'content': 'x'}], None)


if __name__ == '__main__':
    unittest.main()
