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

import logging
from urllib.parse import quote

import pytest

from discord.http import Route
from discord.webhook.async_ import AsyncWebhookAdapter
from discord.webhook.sync import WebhookAdapter


def test_route_url_for_log_redacts_webhook_token():
    token = 'poc-secret/webhook-token?value'
    route = Route('POST', '/webhooks/{webhook_id}/{webhook_token}', webhook_id=123456789012345, webhook_token=token)

    assert quote(token, safe='') in route.url
    logged_url = route._url_for_log()
    assert token not in logged_url
    assert '<redacted>' in logged_url


@pytest.mark.asyncio
async def test_async_webhook_log_does_not_contain_webhook_token(caplog):
    class Response:
        status = 204
        headers = {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            pass

        async def text(self, encoding='utf-8'):
            return ''

    class Session:
        def request(self, *args, **kwargs):
            return Response()

    token = 'poc-secret/webhook-token?value'
    route = Route('POST', '/webhooks/{webhook_id}/{webhook_token}', webhook_id=123456789012345, webhook_token=token)

    with caplog.at_level(logging.DEBUG, logger='discord.webhook.async_'):
        await AsyncWebhookAdapter().request(route, Session())

    assert token not in caplog.text
    assert '<redacted>' in caplog.text


def test_sync_webhook_log_does_not_contain_webhook_token(caplog):
    class Response:
        status_code = 204
        headers = {}
        encoding = None
        text = ''

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            pass

    class Session:
        def request(self, *args, **kwargs):
            return Response()

    token = 'poc-secret/webhook-token?value'
    route = Route('POST', '/webhooks/{webhook_id}/{webhook_token}', webhook_id=123456789012345, webhook_token=token)

    with caplog.at_level(logging.DEBUG, logger='discord.webhook.sync'):
        WebhookAdapter().request(route, Session())

    assert token not in caplog.text
    assert '<redacted>' in caplog.text
