"""Hermes endpoint adapter for the assistant pane.

The assistant is advisory by law: it explains, drafts, and interprets. It
never verifies. A translation is accepted because it ran and its numbers
matched, so every reply the workbench shows carries an advisory banner, and
this module is the only code path that talks to an LLM endpoint.

Configuration is environment only, nothing lives in the tree:
  SASCHI_HERMES_URL       base URL of an OpenAI-compatible API (e.g. http://host:port/v1)
  SASCHI_HERMES_API_KEY   bearer token for that endpoint
  SASCHI_HERMES_MODEL     model name (optional, defaults to 'default')
When SASCHI_HERMES_URL and SASCHI_HERMES_API_KEY are not both set, the
assistant is off and the pane says so. No network call is made unless it is.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Mapping

DEFAULT_TIMEOUT = 120.0
TEMPERATURE = 0.2

SYSTEM_PROMPT = (
    "You are the SAS translation assistant for SASchi-Go, an open toolkit that "
    "reproduces SAS behavior in Python, R, and C++ with verification receipts. "
    "Your role is advisory: you explain SAS constructs, explain how the "
    "translator routes them through its rulebook, draft candidate conversions, "
    "and interpret review tickets and receipts in plain language. "
    "You never declare a translation correct, verified, or accepted. "
    "Verification happens only in the tool's gates: a translation is accepted "
    "because it ran and its numbers matched the documented rule, not because "
    "you said so. When you draft code, say it is a candidate for the gates to "
    "check. Be direct, technical, and brief."
)


class AssistantNotConfigured(RuntimeError):
    """The assistant is off: no endpoint is configured."""


class AssistantError(RuntimeError):
    """The endpoint was configured but the call failed."""


def hermes_config(env: "Mapping[str, str] | None" = None) -> "dict | None":
    """Read the endpoint configuration, or None when the assistant is off."""
    env = os.environ if env is None else env
    url = (env.get('SASCHI_HERMES_URL') or '').strip().rstrip('/')
    key = (env.get('SASCHI_HERMES_API_KEY') or '').strip()
    if not url or not key:
        return None
    model = (env.get('SASCHI_HERMES_MODEL') or '').strip() or 'default'
    return {'base_url': url, 'api_key': key, 'model': model}


def chat(messages: list, config: "dict | None" = None, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """One turn against the endpoint. Returns the reply with its advisory flag."""
    config = config or hermes_config()
    if not config:
        raise AssistantNotConfigured(
            'assistant not configured: set SASCHI_HERMES_URL and SASCHI_HERMES_API_KEY')
    payload = json.dumps({'model': config['model'], 'messages': messages,
                          'temperature': TEMPERATURE, 'stream': False}).encode('utf-8')
    request = urllib.request.Request(
        config['base_url'] + '/chat/completions', data=payload,
        headers={'Authorization': 'Bearer ' + config['api_key'],
                 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        raise AssistantError(f'endpoint returned HTTP {exc.code}') from exc
    except (OSError, ValueError) as exc:
        raise AssistantError(f'endpoint unreachable: {exc}') from exc
    try:
        reply = body['choices'][0]['message']['content']
    except (KeyError, IndexError, TypeError) as exc:
        raise AssistantError('endpoint response is missing choices[0].message.content') from exc
    return {'reply': reply, 'model': body.get('model', config['model']),
            'provider': 'hermes', 'advisory': True,
            'status_line': 'assistant output; not a verified translation. the gates verify.'}


def assistant_context(context: "str | None" = None) -> list:
    """System prompt plus any program context the pane attached."""
    messages = [{'role': 'system', 'content': SYSTEM_PROMPT}]
    if context:
        messages.append({'role': 'system',
                         'content': 'Program and stage context from the workbench, for reference:\n' + context})
    return messages
