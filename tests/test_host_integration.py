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
    from hermes_cli import plugins
    from hermes_cli.plugins import get_plugin_manager
    from hermes_cli.plugins_manifest import parse_manifest_file
    token = set_hermes_home_override(tmp_path)
    root = Path(__file__).resolve().parents[1]
    config = {'plugins': {'enabled': ['hermes-jev-reply-gate'], 'entries': {
        'hermes-jev-reply-gate': {'settings': {'enabled': True, 'mode': 'suppress',
            'telegram': {'group_ids': ['-100123']}}}}}}
    (tmp_path / 'config.yaml').write_text(json.dumps(config))
    monkeypatch.setattr(plugins, '_plugin_managers_by_home', {})
    monkeypatch.setattr(plugins, '_plugin_manager', None)
    manager = get_plugin_manager()
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
            assert (await callback(event))['action'] == 'observe'
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


@pytest.fixture
def host_pipeline(loaded_plugin, monkeypatch):
    """Real host state/profile scope; only network and authorization policy are replaced."""
    from types import SimpleNamespace
    from gateway.config import GatewayConfig, Platform
    from gateway.platforms.event import MessageEvent
    from gateway.run import GatewayRunner
    from gateway.session import SessionSource, SessionStore
    from gateway.session_identity import RoutingIdentity
    from hermes_state import SessionDB
    manager, callback, profile = loaded_plugin
    (profile / '.env').write_text('TYPESAFE_API_KEY=synthetic-profile-key\n')
    source = SessionSource(platform=Platform.TELEGRAM, chat_id='-100123', user_id='42',
                           user_name='Sam', chat_type='group')
    source._identity = RoutingIdentity('default', 'default', profile, profile)
    store = SessionStore(sessions_dir=profile / 'sessions', config=GatewayConfig())
    store._db = SessionDB(profile / 'state.db')
    entry = store.get_or_create_session(source)
    store._db.append_message(entry.session_id, 'user', '[Sam|42]: earlier', platform_message_id='previous')
    runner = object.__new__(GatewayRunner)
    runner.config = GatewayConfig(multiplex_profiles=True)
    runner.session_store = store
    runner._is_user_authorized_for_source = lambda source: source.user_id == '42'
    seen = []
    def serve(request):
        seen.append(request)
        return httpx.Response(200, json=response_body())
    callback.__self__.gate.client._transport = httpx.MockTransport(serve)
    def make_event(**changes):
        values = dict(text='chatter', message_id='current', reply_expected=False, source=source)
        values.update(changes)
        return MessageEvent(**values)
    try:
        yield SimpleNamespace(manager=manager, callback=callback, profile=profile, source=source,
                              store=store, entry=entry, runner=runner, seen=seen, event=make_event)
    finally:
        store._db.close()


@pytest.mark.asyncio
async def test_denied_actual_author_from_shared_source_is_not_disclosed(host_pipeline):
    from gateway import ingress
    from gateway.session_identity import replace_source
    p = host_pipeline
    inspected = []
    def authorized(source):
        inspected.append(source.user_id)
        return source.user_id == '42'
    p.runner._is_user_authorized_for_source = authorized
    shared = replace_source(p.source, user_id=None, user_name=None)
    event = p.event(source=shared, user_id='denied-sender', user_name='Untrusted')
    assert await ingress.evaluate(p.runner, event, p.entry.session_key, 'previous') is False
    assert inspected == ['denied-sender']
    assert p.seen == []
    assert len(p.store._db.get_messages(p.entry.session_id)) == 1


@pytest.mark.parametrize('changes', [
    {'reply_expected': None}, {'reply_expected': True},
    {'media_urls': ['synthetic-image.png']}, {'reply_to_is_own_message': True},
    {'prompt_response': {'prompt_id': 'synthetic', 'option_id': 'yes'}},
    {'message_type': 'photo'},
])
@pytest.mark.asyncio
async def test_host_bypasses_addressed_unknown_control_and_media_without_http(host_pipeline, changes):
    from gateway import ingress
    from gateway.platforms.event import MessageType
    p = host_pipeline
    changes = dict(changes)
    if 'message_type' in changes:
        changes['message_type'] = MessageType.PHOTO
    assert await ingress.evaluate(p.runner, p.event(**changes), p.entry.session_key, 'previous') is False
    assert p.seen == []
    assert len(p.store._db.get_messages(p.entry.session_id)) == 1


@pytest.mark.parametrize('command', ['/stop', '/new', '/help', '/approve'])
@pytest.mark.asyncio
async def test_real_ingress_queue_commands_bypass_policy_without_http(host_pipeline, command):
    from types import SimpleNamespace
    from gateway import ingress
    p = host_pipeline
    adapter = SimpleNamespace(_background_tasks=set())
    async def policy(event, key, previous, deadline):
        return await ingress.evaluate(p.runner, event, key, previous, deadline)
    queue = ingress.IngressQueue(adapter, policy)
    assert await queue.submit(p.event(text=command), p.entry.session_key) is False
    assert p.seen == []
    assert not queue.tasks
    assert not adapter._background_tasks


from contextlib import asynccontextmanager


@asynccontextmanager
async def pending_interaction(pipeline, kind):
    """Create actual host control state and settle it through its normal API."""
    import asyncio
    from tools import approval, clarify_gateway, slash_confirm
    from tools.approval_gateway_wait import _await_gateway_decision
    p, key = pipeline, pipeline.entry.session_key
    waiter = None
    if kind in ('clarify', 'choice'):
        clarify_gateway.register('test-clarify', key, 'Continue?', ['Yes', 'No'] if kind == 'choice' else None)
    elif kind == 'slash':
        async def handle(choice):
            return None
        slash_confirm.register(key, 'test-confirm', 'reload-mcp', handle)
    elif kind == 'update':
        p.runner._session_state(key).persistent.update_prompt_pending = True
    elif kind == 'approval':
        loop, entered = asyncio.get_running_loop(), asyncio.Event()
        waiter = asyncio.create_task(asyncio.to_thread(
            _await_gateway_decision, key, lambda data: loop.call_soon_threadsafe(entered.set),
            {'command': 'synthetic nonexecuting operation', 'description': 'Test prompt', 'pattern_key': 'test'}))
        await asyncio.wait_for(entered.wait(), 2)
    try:
        yield
    finally:
        if kind in ('clarify', 'choice'):
            clarify_gateway.resolve_gateway_clarify('test-clarify', 'test complete')
            clarify_gateway.wait_for_response('test-clarify', .01)
        elif kind == 'slash':
            slash_confirm.clear(key)
        elif kind == 'update':
            p.runner._session_state(key).persistent.update_prompt_pending = False
        elif kind == 'approval':
            approval.resolve_gateway_approval(key, 'deny', resolve_all=True)
            await asyncio.wait_for(waiter, 2)


@pytest.mark.parametrize('kind', ['clarify', 'choice', 'approval', 'update', 'slash'])
@pytest.mark.asyncio
async def test_pending_host_interactions_bypass_before_disclosure(host_pipeline, kind):
    from gateway import ingress
    p = host_pipeline
    async with pending_interaction(p, kind):
        assert await ingress.evaluate(p.runner, p.event(text='yes'), p.entry.session_key, 'previous') is False
    assert p.seen == []
    assert len(p.store._db.get_messages(p.entry.session_id)) == 1


@pytest.mark.parametrize('kind', ['clarify', 'choice', 'approval', 'update', 'slash'])
@pytest.mark.asyncio
async def test_pending_interaction_created_during_http_prevents_observation(host_pipeline, kind):
    import asyncio
    from gateway import ingress
    p = host_pipeline
    reached, release = asyncio.Event(), asyncio.Event()
    async def serve(request):
        p.seen.append(request)
        reached.set()
        await release.wait()
        return httpx.Response(200, json=response_body())
    p.callback.__self__.gate.client._transport = httpx.MockTransport(serve)
    task = asyncio.create_task(ingress.evaluate(p.runner, p.event(), p.entry.session_key, 'previous'))
    await asyncio.wait_for(reached.wait(), 1)
    async with pending_interaction(p, kind):
        release.set()
        assert await task is False
    assert len(p.seen) == 1
    assert len(p.store._db.get_messages(p.entry.session_id)) == 1
    assert not p.store._dirty_transcripts


@pytest.mark.parametrize('previous', [None, 'unpersisted-inbound'])
@pytest.mark.asyncio
async def test_active_unpersisted_input_fails_open_without_disclosure(host_pipeline, previous):
    from gateway import ingress
    p = host_pipeline
    p.runner._session_state(p.entry.session_key).turn.agent = object()
    assert await ingress.evaluate(p.runner, p.event(), p.entry.session_key, previous) is False
    assert p.seen == []
    assert len(p.store._db.get_messages(p.entry.session_id)) == 1


@pytest.mark.asyncio
async def test_another_normalized_transport_uses_host_contract_but_not_jev_scope(host_pipeline):
    from gateway import ingress
    from gateway.config import Platform
    from gateway.session_identity import replace_source
    from hermes_cli.plugins import PluginContext, PluginManifest
    p = host_pipeline
    source = replace_source(p.source, platform=Platform.DISCORD)
    entry = p.store.get_or_create_session(source)
    event = p.event(source=source)
    assert await ingress.evaluate(p.runner, event, entry.session_key, None) is False
    assert p.seen == []
    p.manager.unload('hermes-jev-reply-gate')
    received = []
    async def synthetic_policy(request):
        received.append(request)
        return {'action': 'observe'}
    context = PluginContext(PluginManifest(name='synthetic-policy'), p.manager)
    context.register_ingress_policy(synthetic_policy)
    assert await ingress.evaluate(p.runner, event, entry.session_key, None) is True
    assert received[0].platform == 'discord'
    rows = p.store._db.get_messages(entry.session_id)
    assert len(rows) == 1
    assert rows[0]['observed'] == 1
    assert rows[0]['content'] == '[Sam|42]\nchatter'
    assert p.seen == []


@pytest.mark.asyncio
async def test_real_a_b_a_runtime_homes_keep_settings_secrets_and_transcripts_isolated(host_pipeline, monkeypatch):
    from gateway import ingress
    from gateway.config import GatewayConfig
    from gateway.run import _async_profile_runtime_scope
    from gateway.session import SessionStore
    from gateway.session_identity import RoutingIdentity, replace_source
    from hermes_cli.plugins import get_plugin_manager
    from hermes_state import SessionDB
    p = host_pipeline
    home_b = p.profile / 'profile-b'
    home_b.mkdir()
    config_b = json.loads((p.profile / 'config.yaml').read_text())
    settings_b = config_b['plugins']['entries']['hermes-jev-reply-gate']['settings']
    settings_b.update(mode='shadow', context_messages=1)
    (home_b / 'config.yaml').write_text(json.dumps(config_b))
    (home_b / '.env').write_text('TYPESAFE_API_KEY=synthetic-profile-b-key\n')
    source_b = replace_source(p.source, profile='profile-b')
    source_b._identity = RoutingIdentity('profile-b', 'profile-b', home_b, home_b)
    seen = []
    def serve(request):
        seen.append((request.headers['authorization'], json.loads(request.content)))
        return httpx.Response(200, json=response_body())
    p.callback.__self__.gate.client._transport = httpx.MockTransport(serve)
    async with _async_profile_runtime_scope(home_b):
        manager_b = get_plugin_manager()
        assert manager_b is not p.manager
        manifest = p.manager._plugins['hermes-jev-reply-gate'].manifest
        monkeypatch.setattr(manager_b, '_collect_directory_manifests', lambda: [manifest])
        monkeypatch.setattr(manager_b, '_scan_entry_points', lambda: [])
        manager_b.discover_and_load()
        loaded_b = manager_b._plugins['hermes-jev-reply-gate']
        assert loaded_b.error is None, loaded_b.error
        callback_b, = manager_b._hooks['pre_gateway_ingress']
        callback_b.__self__.gate.client._transport = httpx.MockTransport(serve)
        store_b = SessionStore(sessions_dir=home_b / 'sessions', config=GatewayConfig())
        store_b._db = SessionDB(home_b / 'state.db')
        entry_b = store_b.get_or_create_session(source_b)
        store_b._db.append_message(entry_b.session_id, 'user', '[Sam|42]: b-only context', platform_message_id='previous-b')
    runner_b = object.__new__(type(p.runner))
    runner_b.config = p.runner.config
    runner_b.session_store = store_b
    runner_b._is_user_authorized_for_source = p.runner._is_user_authorized_for_source
    try:
        assert await ingress.evaluate(p.runner, p.event(message_id='a-first'), p.entry.session_key, 'previous') is True
        assert await ingress.evaluate(runner_b, p.event(source=source_b, message_id='b-first'), entry_b.session_key, 'previous-b') is False
        assert await ingress.evaluate(p.runner, p.event(message_id='a-second'), p.entry.session_key, 'a-first') is True
        assert [key for key, payload in seen] == [
            'Bearer synthetic-profile-key', 'Bearer synthetic-profile-b-key', 'Bearer synthetic-profile-key']
        assert [len(payload['state']) for key, payload in seen] == [2, 1, 3]
        assert len(p.store._db.get_messages(p.entry.session_id)) == 3
        assert len(store_b._db.get_messages(entry_b.session_id)) == 1
        assert 'b-only context' not in json.dumps([seen[0], seen[2]])
        assert all('earlier' not in row['content'] for row in seen[1][1]['state'])
        async with _async_profile_runtime_scope(p.profile):
            assert get_plugin_manager() is p.manager
        async with _async_profile_runtime_scope(home_b):
            assert get_plugin_manager() is manager_b
    finally:
        manager_b.unload()
        store_b._db.close()


@pytest.mark.parametrize('change', ['disable', 'shadow', 'unload'])
@pytest.mark.asyncio
async def test_change_after_policy_return_before_final_authorization_prevents_commit(host_pipeline, change):
    import asyncio
    import threading
    from gateway import ingress
    p = host_pipeline
    reached, release = asyncio.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    authorizations = []
    def authorized(source):
        authorizations.append(source.user_id)
        if len(authorizations) == 2:
            loop.call_soon_threadsafe(reached.set)
            assert release.wait(2), 'test failed to release final authorization'
        return True
    p.runner._is_user_authorized_for_source = authorized
    task = asyncio.create_task(ingress.evaluate(p.runner, p.event(), p.entry.session_key, 'previous'))
    try:
        await asyncio.wait_for(reached.wait(), 1)
        assert len(p.seen) == 1  # The policy already returned its observe intent.
        if change == 'unload':
            p.manager.unload('hermes-jev-reply-gate')
        else:
            config = json.loads((p.profile / 'config.yaml').read_text())
            settings = config['plugins']['entries']['hermes-jev-reply-gate']['settings']
            settings['enabled' if change == 'disable' else 'mode'] = False if change == 'disable' else 'shadow'
            (p.profile / 'config.yaml').write_text(json.dumps(config))
    finally:
        release.set()
    assert await task is False
    assert len(p.store._db.get_messages(p.entry.session_id)) == 1
    assert not p.store._dirty_transcripts
