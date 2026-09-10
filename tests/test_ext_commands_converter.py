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
from unittest.mock import AsyncMock

import discord
import pytest

from discord.ext.commands.converter import MessageConverter


class FakeMessageable(discord.abc.Messageable):
    def __init__(self, channel_id: int, message: object) -> None:
        self.id = channel_id
        self.fetch_message = AsyncMock(return_value=message)


def make_context(channel: FakeMessageable, cached_message: object) -> SimpleNamespace:
    connection = SimpleNamespace(_get_message=lambda message_id: cached_message)
    bot = SimpleNamespace(
        _connection=connection,
        get_channel=lambda channel_id: channel,
    )
    return SimpleNamespace(bot=bot, channel=channel, guild=None)


@pytest.mark.asyncio
async def test_message_converter_does_not_return_cached_message_from_another_channel():
    message_id = 123456789012345
    channel_id = 200000000000001
    cached_message = SimpleNamespace(channel=SimpleNamespace(id=100000000000001))
    fetched_message = object()
    channel = FakeMessageable(channel_id, fetched_message)
    ctx = make_context(channel, cached_message)

    result = await MessageConverter().convert(ctx, str(message_id))

    assert result is fetched_message
    channel.fetch_message.assert_awaited_once_with(message_id)


@pytest.mark.asyncio
async def test_message_converter_returns_cached_message_from_requested_channel():
    message_id = 123456789012345
    channel_id = 200000000000001
    cached_message = SimpleNamespace(channel=SimpleNamespace(id=channel_id))
    channel = FakeMessageable(channel_id, object())
    ctx = make_context(channel, cached_message)

    result = await MessageConverter().convert(ctx, str(message_id))

    assert result is cached_message
    channel.fetch_message.assert_not_awaited()
