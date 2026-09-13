import asyncio
import copy
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from discord.gateway import DiscordWebSocket, DiscordVoiceWebSocket
from discord.http import HTTPClient, Route
from discord import utils


@pytest.mark.asyncio
@pytest.mark.parametrize('listed', [False, True])
async def test_http_response_logging_preserves_data_but_redacts_credentials(caplog, listed):
    payload = {'id': '123', 'type': 1, 'token': 'test-webhook-token'}
    if listed:
        payload = [payload, {'id': '456', 'token': 'test-second-token'}]

    class Response:
        status = 200
        headers = {'content-type': 'application/json'}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def text(self, **kwargs):
            return json.dumps(payload)

    http = HTTPClient(asyncio.get_running_loop())
    http._HTTPClient__session = SimpleNamespace(request=lambda *a, **kw: Response())
    http._global_over = asyncio.Event()
    http._global_over.set()
    with caplog.at_level(logging.DEBUG, logger='discord.http'):
        result = await (http.channel_webhooks(123) if listed else http.get_webhook(123))
    assert result == payload
    assert 'test-webhook-token' not in caplog.text
    assert 'test-second-token' not in caplog.text
    assert '<redacted>' in caplog.text
    assert '123' in caplog.text
    assert 'test-webhook-token' not in repr([record.args for record in caplog.records])


@pytest.mark.asyncio
@pytest.mark.parametrize('event', ['INTERACTION_CREATE', 'VOICE_SERVER_UPDATE'])
async def test_gateway_logging_does_not_mutate_dispatched_event(caplog, event):
    parsed = []
    raw = []
    ws = DiscordWebSocket(SimpleNamespace(closed=False), loop=asyncio.get_running_loop())
    ws.shard_id = 0
    ws._discord_parsers = {event: parsed.append}
    ws.log_receive = raw.append
    payload = {'op': 0, 't': event, 's': 1, 'd': {'token': 'test-gateway-token', 'id': '123'}}
    message = json.dumps(payload)

    with caplog.at_level(logging.DEBUG, logger='discord.gateway'):
        await ws.received_message(message)

    assert parsed == [payload['d']]
    assert raw == [message]  # Explicit raw debug hooks keep their documented payload.
    assert 'test-gateway-token' not in caplog.text
    assert '<redacted>' in caplog.text
    assert event in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('operation', ['identify', 'resume'])
async def test_voice_send_logs_redacted_data_and_sends_original(caplog, operation):
    socket = SimpleNamespace(send_str=AsyncMock())
    ws = DiscordVoiceWebSocket(socket, asyncio.get_running_loop())
    ws._connection = SimpleNamespace(
        token='test-voice-token', server_id=1, session_id='test-session',
        user=SimpleNamespace(id=1), max_dave_protocol_version=1,
    )
    with caplog.at_level(logging.DEBUG, logger='discord.gateway'):
        await getattr(ws, operation)()
    sent = json.loads(socket.send_str.call_args.args[0])
    assert sent['d']['token'] == 'test-voice-token'
    assert 'test-voice-token' not in caplog.text
    assert '<redacted>' in caplog.text
    assert 'server_id' in caplog.text


@pytest.mark.asyncio
async def test_voice_session_key_stays_available_but_is_not_logged(caplog):
    ws = DiscordVoiceWebSocket(SimpleNamespace(send_str=AsyncMock()), asyncio.get_running_loop())
    ws._connection = SimpleNamespace(ssrc=1)
    key = list(range(32))
    payload = {'op': ws.SESSION_DESCRIPTION, 'd': {
        'secret_key': key, 'mode': 'aead_xchacha20_poly1305_rtpsize', 'dave_protocol_version': 0,
    }}
    original = copy.deepcopy(payload)
    with caplog.at_level(logging.DEBUG, logger='discord.gateway'):
        await ws.received_message(payload)
    assert payload == original
    assert ws.secret_key == key
    assert str(key) not in caplog.text
    assert '<redacted>' in caplog.text
    assert 'aead_xchacha20_poly1305_rtpsize' in caplog.text


@pytest.mark.asyncio
async def test_nested_voice_payload_and_ordinary_fields(caplog):
    socket = SimpleNamespace(send_str=AsyncMock())
    ws = DiscordVoiceWebSocket(socket, asyncio.get_running_loop())
    payload = {'op': 99, 'd': [{'token': 'nested-secret'}, {'secret_key': [71, 72], 'name': 'visible'}]}
    original = copy.deepcopy(payload)
    with caplog.at_level(logging.DEBUG, logger='discord.gateway'):
        await ws.send_as_json(payload)
    assert json.loads(socket.send_str.call_args.args[0]) == original
    assert payload == original
    assert 'nested-secret' not in caplog.text
    assert '[71, 72]' not in caplog.text
    assert 'visible' in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('serialized', [False, True])
async def test_http_retry_logs_hide_url_and_request_tokens(caplog, serialized):
    requests = []

    class Response:
        def __init__(self, status):
            self.status = status
            self.headers = {'content-type': 'application/json', 'Via': 'test'}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def text(self, **kwargs):
            return json.dumps({'retry_after': 0, 'global': False} if self.status == 429 else {'ok': True})

    def request(method, url, **kwargs):
        requests.append((url, kwargs))
        return Response(429 if len(requests) == 1 else 200)

    http = HTTPClient(asyncio.get_running_loop())
    http._HTTPClient__session = SimpleNamespace(request=request)
    http._global_over = asyncio.Event()
    http._global_over.set()
    route = Route('POST', '/webhooks/{webhook_id}/{webhook_token}', webhook_id=123, webhook_token='url-secret/?')
    payload = {'nested': [{'token': 'request-secret'}], 'content': 'visible'}
    # JSON escapes must be decoded for redaction but the wire bytes must not change.
    encoded = json.dumps(payload).replace('token', r't\u006fken')
    kwargs = {'data': encoded} if serialized else {'json': payload}

    with caplog.at_level(logging.DEBUG, logger='discord.http'):
        result = await http.request(route, **kwargs)
    assert result == {'ok': True}
    assert len(requests) == 2
    assert all(url == route.url for url, _ in requests)
    assert all(json.loads(kwargs['data']) == payload for _, kwargs in requests)
    if serialized:
        assert requests[0][1]['data'] == encoded
    assert 'url-secret' not in caplog.text
    assert 'request-secret' not in caplog.text
    assert '<redacted>' in caplog.text
    assert 'visible' in caplog.text
    assert 'request-secret' not in repr([record.args for record in caplog.records])
    assert route.major_parameters.endswith('url-secret/?')


def test_redaction_preserves_non_json_and_nested_tuples():
    assert utils._redact_sensitive_data('plain text', serialized=True) == 'plain text'
    data = ({'token': 'secret', 'name': 'visible'},)
    assert utils._redact_sensitive_data(data) == ({'token': '<redacted>', 'name': 'visible'},)
    assert data[0]['token'] == 'secret'


@pytest.mark.asyncio
async def test_disabled_debug_logging_does_not_build_a_projection(monkeypatch, caplog):
    def unexpected(*args, **kwargs):
        raise AssertionError('Logging projection should only be built at DEBUG')

    monkeypatch.setattr(utils, '_redact_sensitive_data', unexpected)
    socket = SimpleNamespace(send_str=AsyncMock())
    ws = DiscordVoiceWebSocket(socket, asyncio.get_running_loop())
    with caplog.at_level(logging.INFO, logger='discord.gateway'):
        await ws.send_as_json({'op': 3, 'd': 1})
    socket.send_str.assert_awaited_once()
