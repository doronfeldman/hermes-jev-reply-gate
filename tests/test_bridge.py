import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
import json
import logging

import httpx
import pytest

from reply_gate import hermes_bridge as bridge
from reply_gate.engine import ReplyGate
from reply_gate.jev import JevClient
from test_jev import response_body


@dataclass(frozen=True)
class Request:
    platform: str = 'telegram'
    chat_id: str = '-100123'
    session_key: str = 'private-session-id'
    message_id: str = 'private-message-id'
    text: str = '[Private Name|12345]: private-message'
    history: tuple = ()
    reply_expected: bool | None = False


class Context:
    def __init__(self, settings=None):
        self.settings = {'enabled': True, 'mode': 'suppress', 'telegram': {'group_ids': ['-100123']}}
        if settings:
            self.settings.update(settings)
        self.callbacks = []
        self.unload_callbacks = []
    def get_config(self, key, default=None):
        return self.settings.get(key, default)
    def register_ingress_policy(self, callback):
        self.callbacks.append(callback)
    def on_unload(self, callback):
        self.unload_callbacks.append(callback)


def policy(monkeypatch, ctx=None, handler=None):
    seen = []
    def serve(request):
        seen.append(request)
        return httpx.Response(200, json=response_body())
    monkeypatch.setattr(bridge, 'profile_secret', lambda: 'private-secret')
    gate = ReplyGate(JevClient(transport=httpx.MockTransport(handler or serve)))
    instance = bridge.IngressPolicy(ctx or Context(), gate=gate)
    return instance, seen


def test_registration_validates_settings_and_refuses_old_host(monkeypatch):
    with pytest.raises(RuntimeError, match='register_ingress_policy'):
        bridge.register(object())
    ctx = Context({'mode': 'incorrect'})
    with pytest.raises(ValueError):
        bridge.register(ctx)
    assert ctx.callbacks == []
    ctx = Context()
    bridge.register(ctx)
    assert len(ctx.callbacks) == len(ctx.unload_callbacks) == 1


@pytest.mark.parametrize('settings,event', [
    ({'enabled': False}, Request()), ({'telegram': {'group_ids': []}}, Request()),
    ({}, Request(chat_id='-100456')), ({}, Request(platform='slack')),
    ({}, Request(reply_expected=None)), ({}, Request(reply_expected=True)),
    ({}, Request(text='')), ({'mode': 'bad'}, Request()),
])
@pytest.mark.asyncio
async def test_ineligible_requests_never_disclose_content(monkeypatch, settings, event):
    ctx = Context()
    instance, seen = policy(monkeypatch, ctx)
    ctx.settings.update(settings)
    assert await instance(event) == {'action': 'allow'}
    assert seen == []


@pytest.mark.asyncio
async def test_missing_key_does_not_fall_back_to_environment(monkeypatch):
    instance, seen = policy(monkeypatch)
    monkeypatch.setenv('TYPESAFE_API_KEY', 'ambient-secret')
    monkeypatch.setattr(bridge, 'profile_secret', lambda: None)
    assert await instance(Request()) == {'action': 'allow'}
    assert seen == []


@pytest.mark.asyncio
async def test_suppression_returns_only_intent_and_logs_bounded_metadata(monkeypatch, caplog):
    instance, seen = policy(monkeypatch)
    with caplog.at_level(logging.INFO, logger='hermes.plugins.hermes-jev-reply-gate'):
        assert await instance(Request()) == {'action': 'observe'}
    payload = json.loads(seen[0].content)
    assert payload['state'][0]['content'] == 'Speaker 1: private-message'
    for forbidden in ('private-secret', 'private-message', 'private-session-id', '12345', '-100123', 'Private Name'):
        assert forbidden not in caplog.text
    event = json.loads(caplog.records[-1].message)
    assert event['reason'] == 'confident_ignore'
    assert event['action'] == 'observe'
    assert event['probabilities']['IGNORE'] == .97
    assert event['elapsed_ms'] >= 0


@pytest.mark.asyncio
async def test_runtime_config_rechecked_after_network_and_retained_callback_inert(monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    async def serve(request):
        entered.set()
        await release.wait()
        return httpx.Response(200, json=response_body())
    ctx = Context()
    instance, _ = policy(monkeypatch, ctx, serve)
    task = asyncio.create_task(instance(Request()))
    await entered.wait()
    ctx.settings['enabled'] = False
    release.set()
    assert await task == {'action': 'allow'}
    ctx.settings['enabled'] = True
    instance.close()
    assert await instance(Request()) == {'action': 'allow'}


@pytest.mark.asyncio
async def test_shadow_records_would_ignore_without_observe(monkeypatch, caplog):
    instance, _ = policy(monkeypatch, Context({'mode': 'shadow'}))
    with caplog.at_level(logging.INFO, logger='hermes.plugins.hermes-jev-reply-gate'):
        assert await instance(Request()) == {'action': 'allow'}
    assert json.loads(caplog.records[-1].message)['reason'] == 'would_ignore'


@pytest.mark.asyncio
async def test_runtime_scope_key_isolation_a_b_a(monkeypatch):
    key = ContextVar('key')
    instance, seen = policy(monkeypatch)
    monkeypatch.setattr(bridge, 'profile_secret', key.get)
    for secret in ('a', 'b', 'a'):
        token = key.set(secret)
        try:
            assert await instance(Request()) == {'action': 'observe'}
        finally:
            key.reset(token)
    assert [request.headers['authorization'] for request in seen] == ['Bearer a', 'Bearer b', 'Bearer a']


@pytest.mark.asyncio
async def test_concurrent_sessions_bound_and_cancel_releases_slot(monkeypatch):
    entered = asyncio.Event()
    async def serve(request):
        entered.set()
        await asyncio.Event().wait()
    instance, _ = policy(monkeypatch, Context({'max_sessions': 1}), serve)
    task = asyncio.create_task(instance(Request()))
    await entered.wait()
    assert await instance(Request(session_key='other')) == {'action': 'allow'}
    assert await instance(Request()) == {'action': 'allow'}
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    entered.clear()
    task = asyncio.create_task(instance(Request(session_key='other')))
    await asyncio.wait_for(entered.wait(), .2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_unrelated_session_proceeds_while_first_stalls(monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    async def serve(request):
        if 'first' in request.content.decode():
            entered.set()
            await release.wait()
        return httpx.Response(200, json=response_body())
    instance, _ = policy(monkeypatch, handler=serve)
    task = asyncio.create_task(instance(Request(text='first')))
    await entered.wait()
    assert await asyncio.wait_for(instance(Request(session_key='other', text='second')), .2) == {'action': 'observe'}
    release.set()
    assert await task == {'action': 'observe'}


@pytest.mark.asyncio
async def test_unload_during_request_prevents_late_observe(monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    async def serve(request):
        entered.set()
        await release.wait()
        return httpx.Response(200, json=response_body())
    instance, _ = policy(monkeypatch, handler=serve)
    task = asyncio.create_task(instance(Request()))
    await entered.wait()
    instance.close()
    release.set()
    assert await task == {'action': 'allow'}
