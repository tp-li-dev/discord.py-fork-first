"""
The MIT License (MIT)

Copyright (c) 2015-present Rapptz

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

from types import SimpleNamespace

import aiohttp
import pytest
import yarl

from discord.gateway import DiscordWebSocket


@pytest.mark.asyncio
async def test_gateway_fallback_preserves_query_parameters(monkeypatch):
    urls = []
    socket = SimpleNamespace(closed=False)

    async def ws_connect(url):
        urls.append(yarl.URL(url))
        if len(urls) == 1:
            raise aiohttp.WSServerHandshakeError(
                request_info=SimpleNamespace(real_url=urls[0]),
                history=(),
                status=503,
                message='Service Unavailable',
                headers={},
            )
        return socket

    identified = []
    resumed = []

    async def poll_event(self):
        pass

    async def identify(self):
        identified.append(True)

    async def resume(self):
        resumed.append(True)

    monkeypatch.setattr(DiscordWebSocket, 'poll_event', poll_event)
    monkeypatch.setattr(DiscordWebSocket, 'identify', identify)
    monkeypatch.setattr(DiscordWebSocket, 'resume', resume)

    connection = SimpleNamespace(
        parsers={},
        call_hooks=None,
        shard_count=None,
        heartbeat_timeout=60.0,
        _update_references=lambda ws: None,
    )
    client = SimpleNamespace(
        http=SimpleNamespace(token='token', ws_connect=ws_connect),
        loop=None,
        _connection=connection,
        dispatch=lambda *args: None,
        _enable_debug_events=False,
    )
    gateway = yarl.URL('wss://resume.example.test/')

    result = await DiscordWebSocket.from_client(client, gateway=gateway, resume=True)

    assert result.gateway == DiscordWebSocket.DEFAULT_GATEWAY
    assert urls[0].query == urls[1].query
    assert urls[1].query['v'] == '10'
    assert urls[1].query['encoding'] == 'json'
    assert urls[1].query['compress'] == 'zstd-stream'
    assert identified == [True]
    assert not resumed
