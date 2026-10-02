import asyncio
import copy
import json

import httpx
import pytest

from reply_gate.jev import JevClient, JevError


def response_body():
    return {'model': 'jev-1.13.0', 'answers': {'reply_action': {
        'type': 'choice', 'choice': 'IGNORE', 'confidence': .92,
        'probabilities': {'ANSWER': .02, 'IGNORE': .97, 'UNCERTAIN': .01},
    }}, 'usage': {'input_tokens': 42, 'output_tokens': 20}}


@pytest.mark.asyncio
async def test_real_http_payload_key_isolation_and_valid_ignore():
    seen = []
    def serve(request):
        seen.append(request)
        return httpx.Response(200, json=response_body())
    client = JevClient(transport=httpx.MockTransport(serve))
    state = [{'role': 'user', 'content': 'Speaker 1: hello', 'latest': True}]
    for key in ('key-a', 'key-b', 'key-a'):
        answer = await client.classify(state, api_key=key, timeout_seconds=.5)
        assert answer.choice == 'IGNORE'
        assert answer.probabilities['IGNORE'] == .97
    assert [r.headers['authorization'] for r in seen] == ['Bearer key-a', 'Bearer key-b', 'Bearer key-a']
    assert all(str(r.url) == 'https://api.typesafe.ai/v1/systemone' for r in seen)
    payload = json.loads(seen[0].content)
    assert payload['model'] == 'jev-1.13.0'
    assert payload['state'] == state
    assert set(payload['questions']['reply_action']['criteria']) == {'ANSWER', 'IGNORE', 'UNCERTAIN'}
    assert 'key-a' not in seen[0].content.decode()


@pytest.mark.parametrize('patch', [
    lambda d: d.update(model='jev-latest'),
    lambda d: d['answers'].update(reply_action=[]),
    lambda d: d['answers']['reply_action'].update(type='score'),
    lambda d: d['answers']['reply_action'].update(choice='OTHER'),
    lambda d: d['answers']['reply_action'].update(choice=[]),
    lambda d: d['answers']['reply_action'].pop('probabilities'),
    lambda d: d['answers']['reply_action']['probabilities'].pop('ANSWER'),
    lambda d: d['answers']['reply_action']['probabilities'].update(EXTRA=0),
    lambda d: d['answers']['reply_action']['probabilities'].update(IGNORE=True),
    lambda d: d['answers']['reply_action']['probabilities'].update(IGNORE='0.97'),
    lambda d: d['answers']['reply_action']['probabilities'].update(IGNORE=float('nan')),
    lambda d: d['answers']['reply_action']['probabilities'].update(IGNORE=float('inf')),
    lambda d: d['answers']['reply_action']['probabilities'].update(IGNORE=1.01),
    lambda d: d['answers']['reply_action']['probabilities'].update(IGNORE=-.01),
    lambda d: d['answers']['reply_action']['probabilities'].update(IGNORE=.6),
    lambda d: d['answers']['reply_action'].update(choice='ANSWER'),
    lambda d: d['answers']['reply_action'].update(confidence=True),
])
@pytest.mark.asyncio
async def test_malformed_responses_have_safe_failure_category(patch):
    body = response_body()
    patch(body)
    transport = httpx.MockTransport(lambda r: httpx.Response(200, content=json.dumps(body)))
    with pytest.raises(JevError, match='^invalid_response$'):
        await JevClient(transport=transport).classify([], api_key='secret', timeout_seconds=.5)


@pytest.mark.asyncio
async def test_probability_rounding_tolerance():
    body = response_body()
    body['answers']['reply_action']['probabilities'] = {'ANSWER': .01, 'IGNORE': .98, 'UNCERTAIN': 0}
    client = JevClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    assert (await client.classify([], api_key='secret', timeout_seconds=.5)).choice == 'IGNORE'


@pytest.mark.parametrize('status,content,reason', [
    (503, b'private-body', 'http_error'), (302, b'private-body', 'http_error'),
    (200, b'private-body', 'invalid_response'), (200, b'[]', 'invalid_response'),
    (200, b'x' * 17000, 'response_too_large'),
])
@pytest.mark.asyncio
async def test_network_response_errors_are_bounded_without_retry(status, content, reason):
    calls = []
    def serve(request):
        calls.append(request)
        return httpx.Response(status, content=content)
    with pytest.raises(JevError, match=f'^{reason}$'):
        await JevClient(transport=httpx.MockTransport(serve)).classify([], api_key='secret', timeout_seconds=.5)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_outer_deadline_cancels_stalled_transport():
    finished = asyncio.Event()
    async def serve(request):
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()
    with pytest.raises(JevError, match='^timeout$'):
        await JevClient(transport=httpx.MockTransport(serve)).classify([], api_key='secret', timeout_seconds=.02)
    assert finished.is_set()


@pytest.mark.asyncio
async def test_caller_cancellation_is_preserved_and_client_closed():
    started = asyncio.Event()
    class Transport(httpx.AsyncBaseTransport):
        closed = False
        async def handle_async_request(self, request):
            started.set()
            await asyncio.Event().wait()
        async def aclose(self):
            self.closed = True
    transport = Transport()
    task = asyncio.create_task(JevClient(transport=transport).classify([], api_key='secret', timeout_seconds=1))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert transport.closed


@pytest.mark.asyncio
async def test_connection_failure_does_not_expose_exception_details():
    def serve(request):
        raise httpx.ConnectError('secret private-body', request=request)
    with pytest.raises(JevError, match='^network_error$'):
        await JevClient(transport=httpx.MockTransport(serve)).classify([], api_key='secret', timeout_seconds=.5)
