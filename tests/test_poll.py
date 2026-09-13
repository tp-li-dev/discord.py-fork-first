from datetime import timedelta
from types import SimpleNamespace

import discord
import pytest


@pytest.mark.parametrize('multiple', [False, True])
def test_poll_copy_preserves_options_without_state(multiple):
    poll = discord.Poll('Question', timedelta(hours=3), multiple=multiple)
    poll.add_answer(text='First', emoji='\N{THUMBS UP SIGN}').add_answer(text='Second')
    payload = poll._to_dict()
    poll._message = object()
    poll._state = object()
    poll._finalized = True
    poll._total_votes = 10
    poll.answers[0]._vote_count = 10

    copied = poll.copy()

    assert copied._to_dict() == payload
    assert copied.multiple is multiple
    assert copied.layout_type is poll.layout_type
    assert copied.message is None
    assert copied._state is None
    assert not copied.is_finalized()
    assert copied.total_votes == 0
    assert copied.answers[0] is not poll.answers[0]
    assert copied.answers[0].poll is copied
    copied.add_answer(text='Third')
    assert len(poll.answers) == 2


def test_poll_copy_preserves_unknown_layout():
    # The REST parser preserves unknown enum values for forward compatibility.
    layout = discord.enums.try_enum(discord.PollLayoutType, 999)
    poll = discord.Poll('Question', timedelta(hours=1), layout_type=layout)
    assert poll.copy()._to_dict()['layout_type'] == 999


def make_answer(*, count=1, total=205, guild=None, has_poll=True):
    users = [
        {'id': str(i), 'username': str(i), 'discriminator': '0', 'avatar': None}
        for i in range(1, total + 1)
    ]
    requests = []

    async def get_voters(channel_id, message_id, answer_id, *, after, limit):
        assert (channel_id, message_id, answer_id) == (10, 20, 1)
        requests.append((after, limit))
        return {'users': [u for u in users if after is None or int(u['id']) > after][:limit]}

    state = SimpleNamespace(http=SimpleNamespace(get_poll_answer_voters=get_voters))
    poll = discord.Poll('Question', timedelta(hours=1))
    message = SimpleNamespace(_state=state, channel=SimpleNamespace(id=10), id=20, guild=guild)
    message.poll = poll if has_poll else None
    answer = discord.PollAnswer.from_params(id=1, text='Answer', message=message, poll=poll)
    answer._vote_count = count
    return answer, requests


@pytest.mark.asyncio
@pytest.mark.parametrize('count', [0, 1, 100, 1000])
@pytest.mark.parametrize('has_poll', [False, True])
async def test_voters_without_limit_ignores_cached_count(count, has_poll):
    answer, requests = make_answer(count=count, has_poll=has_poll)
    users = [user async for user in answer.voters()]
    assert len(users) == 205
    assert {user.id for user in users} == set(range(1, 206))
    assert requests == [(None, 100), (100, 100), (200, 100), (205, 100)]


@pytest.mark.asyncio
@pytest.mark.parametrize('limit', [0, 1, 100, 101, 205, 300])
async def test_voters_respects_explicit_limit(limit):
    answer, requests = make_answer()
    users = [user async for user in answer.voters(limit=limit)]
    assert len(users) == min(limit, 205)
    assert len({user.id for user in users}) == len(users)
    assert all(0 < page_limit <= 100 for _, page_limit in requests)
    if limit == 0:
        assert requests == []


@pytest.mark.asyncio
async def test_voters_after_and_cached_member():
    member = SimpleNamespace(id=202)
    guild = SimpleNamespace(get_member=lambda user_id: member if user_id == 202 else None)
    answer, requests = make_answer(guild=guild)
    users = [user async for user in answer.voters(after=discord.Object(id=200))]
    assert {user.id for user in users} == {201, 202, 203, 204, 205}
    assert member in users
    assert requests[0] == (200, 100)


@pytest.mark.asyncio
async def test_voters_empty_page():
    answer, requests = make_answer(total=0)
    assert [user async for user in answer.voters()] == []
    assert requests == [(None, 100)]


@pytest.mark.asyncio
async def test_voters_requires_a_sent_poll():
    poll = discord.Poll('Question', timedelta(hours=1)).add_answer(text='Answer')
    with pytest.raises(discord.ClientException):
        _ = [user async for user in poll.answers[0].voters()]
