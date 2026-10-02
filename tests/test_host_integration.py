"""Opt-in tests against the amended Hermes checkout, with synthetic profile/SQLite."""
import json
import os
from pathlib import Path

import httpx
import pytest

from test_jev import response_body


@pytest.fixture
def loaded_plugin(tmp_path, monkeypatch):
    host = os.environ.get('HERMES_TEST_HOST')
    if not host:
        pytest.skip('Set HERMES_TEST_HOST to the amended Hermes checkout')
    monkeypatch.syspath_prepend(host)
    monkeypatch.setenv('HERMES_HOME', str(tmp_path))
    from hermes_constants import set_hermes_home_override, reset_hermes_home_override
    from hermes_cli.plugins import PluginManager
    from hermes_cli.plugins_manifest import parse_manifest_file
    token = set_hermes_home_override(tmp_path)
    root = Path(__file__).resolve().parents[1]
    config = {'plugins': {'enabled': ['hermes-jev-reply-gate'], 'entries': {
        'hermes-jev-reply-gate': {'settings': {'enabled': True, 'mode': 'suppress',
            'telegram': {'group_ids': ['-100123']}}}}}}
    (tmp_path / 'config.yaml').write_text(json.dumps(config))
    manager = PluginManager()
    manifest = parse_manifest_file(root / 'plugin.yaml', root, 'user', '')
    assert manifest is not None
    monkeypatch.setattr(manager, '_collect_directory_manifests', lambda: [manifest])
    monkeypatch.setattr(manager, '_scan_entry_points', lambda: [])
    manager.discover_and_load()
    loaded = manager._plugins['hermes-jev-reply-gate']
    assert loaded.error is None, loaded.error
    callbacks = manager._hooks['pre_gateway_ingress']
    assert len(callbacks) == 1
    try:
        yield manager, callbacks[0], tmp_path
    finally:
        manager.unload()
        reset_hermes_home_override(token)


@pytest.mark.asyncio
async def test_real_manager_load_scoped_credentials_and_unload(loaded_plugin, monkeypatch):
    from agent.secret_scope import set_secret_scope, reset_secret_scope
    from gateway.ingress import IngressRequest
    manager, callback, profile = loaded_plugin
    seen = []
    def serve(request):
        seen.append(request)
        return httpx.Response(200, json=response_body())
    callback.__self__.gate.client._transport = httpx.MockTransport(serve)
    event = IngressRequest('telegram', '-100123', 'session', 'event', '[Sam|42]: hello', (), False)
    for key in ('scope-a', 'scope-b', 'scope-a'):
        token = set_secret_scope({'TYPESAFE_API_KEY': key}, profile_home=str(profile))
        try:
            assert await callback(event) == {'action': 'observe'}
        finally:
            reset_secret_scope(token)
    assert [r.headers['authorization'] for r in seen] == ['Bearer scope-a', 'Bearer scope-b', 'Bearer scope-a']
    manager.unload('hermes-jev-reply-gate')
    assert not manager._hooks.get('pre_gateway_ingress')
    assert await callback(event) == {'action': 'allow'}


@pytest.mark.asyncio
async def test_real_host_evaluate_commits_one_observation_and_replay_does_not_reclassify(loaded_plugin, monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from agent.secret_scope import set_secret_scope, reset_secret_scope
    from gateway import ingress
    from gateway.config import GatewayConfig, Platform
    from gateway.platforms.event import MessageEvent
    from gateway.session import SessionSource, SessionStore
    from hermes_state import SessionDB
    from hermes_cli import plugins
    manager, callback, profile = loaded_plugin
    store = SessionStore(sessions_dir=profile / 'sessions', config=GatewayConfig())
    store._db = SessionDB(profile / 'state.db')
    source = SessionSource(platform=Platform.TELEGRAM, chat_id='-100123', user_id='42', chat_type='group')
    entry = store.get_or_create_session(source)
    store._db.append_message(entry.session_id, 'user', '[Sam|42]: earlier', platform_message_id='previous')
    seen = []
    def serve(request):
        seen.append(request)
        return httpx.Response(200, json=response_body())
    callback.__self__.gate.client._transport = httpx.MockTransport(serve)
    @asynccontextmanager
    async def scope(source):
        token = set_secret_scope({'TYPESAFE_API_KEY': 'synthetic-key'}, profile_home=str(profile))
        try:
            yield
        finally:
            reset_secret_scope(token)
    runner = SimpleNamespace(session_store=store, _async_profile_scope_for_source=scope,
                             _is_user_authorized_for_source=lambda source: source.user_id == '42',
                             _is_session_running=lambda key: False,
                             _peek_session_state=lambda key: None)
    monkeypatch.setattr(plugins, 'iter_hook_callbacks', lambda name: list(manager._hooks.get(name, ())))
    event = MessageEvent(text='chatter', message_id='current', reply_expected=False, source=source)
    try:
        assert await ingress.evaluate(runner, event, entry.session_key, 'previous') is True
        assert await ingress.evaluate(runner, event, entry.session_key, 'previous') is True
        messages = store._db.get_messages(entry.session_id)
        assert len(messages) == 2
        assert messages[-1]['observed'] == 1
        assert messages[-1]['platform_message_id'] == 'current'
        assert len(seen) == 1
        payload = json.loads(seen[0].content)
        assert [item['content'] for item in payload['state']] == ['Speaker 1: earlier', 'Speaker 1\nchatter']
        assert not store._dirty_transcripts
    finally:
        store._db.close()
