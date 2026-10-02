from dataclasses import dataclass
import json
import subprocess
import sys

import httpx
import pytest

from reply_gate.config import Settings
from reply_gate.engine import ReplyGate
from reply_gate.jev import JevClient
from test_jev import response_body


@dataclass(frozen=True)
class Message:
    role: str
    content: str


def setup_gate(body=None):
    seen = []
    def serve(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=body or response_body())
    return ReplyGate(JevClient(transport=httpx.MockTransport(serve))), seen


@pytest.mark.parametrize('mode,probability,choice,action,reason', [
    ('suppress', .95, 'IGNORE', 'observe', 'confident_ignore'),
    ('suppress', .949, 'IGNORE', 'allow', 'below_threshold'),
    ('shadow', .99, 'IGNORE', 'allow', 'would_ignore'),
    ('suppress', .99, 'ANSWER', 'allow', 'answer'),
    ('suppress', .99, 'UNCERTAIN', 'allow', 'uncertain'),
])
@pytest.mark.asyncio
async def test_policy_only_observes_confident_ignore_in_suppress(mode, probability, choice, action, reason):
    body = response_body()
    answer = body['answers']['reply_action']
    answer['choice'] = choice
    answer['probabilities'] = {label: probability if label == choice else (1-probability)/2
                               for label in ('ANSWER', 'IGNORE', 'UNCERTAIN')}
    gate, seen = setup_gate(body)
    settings = Settings.from_mapping({'mode': mode})
    decision = await gate.evaluate(text='hello', history=(), settings=settings, api_key='key')
    assert (decision.action, decision.reason) == (action, reason)
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_redacts_attribution_consistently_without_identifiers_or_metadata():
    gate, seen = setup_gate()
    history = (Message('user', '[Alice|12345]: old'), Message('assistant', 'Want me to book it?'),
               Message('user', '[Bob|98765]: hi'), Message('tool', 'SECRET'))
    await gate.evaluate(text='[Alice renamed|12345]: כן', history=history, settings=Settings(), api_key='key')
    state = seen[0]['state']
    assert state == [
        {'role': 'user', 'content': 'Speaker 1: old', 'latest': False},
        {'role': 'assistant', 'content': 'Want me to book it?', 'latest': False},
        {'role': 'user', 'content': 'Speaker 2: hi', 'latest': False},
        {'role': 'user', 'content': 'Speaker 1: כן', 'latest': True},
    ]
    serialized = json.dumps(seen)
    assert all(value not in serialized for value in ('Alice', 'Bob', '12345', '98765', 'SECRET'))
    seen.clear()
    await gate.evaluate(text='[Bob|98765]: again', history=(), settings=Settings(), api_key='key')
    assert seen[0]['state'][0]['content'] == 'Speaker 1: again'


@pytest.mark.asyncio
async def test_keeps_complete_recent_suffix_and_does_not_truncate_latest():
    gate, seen = setup_gate()
    settings = Settings.from_mapping({'context_messages': 3, 'context_characters': 15})
    history = (Message('user', 'older'), Message('assistant', 'middle'), Message('user', 'recent'))
    await gate.evaluate(text='latest', history=history, settings=settings, api_key='key')
    assert [row['content'] for row in seen[0]['state']] == ['recent', 'latest']
    seen.clear()
    decision = await gate.evaluate(text='x' * 16, history=(), settings=settings, api_key='key')
    assert decision.action == 'allow'
    assert decision.reason == 'context_budget'
    assert seen == []


@pytest.mark.asyncio
async def test_message_budget_and_identical_text_are_not_content_deduplicated():
    gate, seen = setup_gate()
    settings = Settings.from_mapping({'context_messages': 2})
    await gate.evaluate(text='yes', history=(Message('assistant', 'confirm?'), Message('user', 'yes')),
                        settings=settings, api_key='key')
    assert [row['content'] for row in seen[0]['state']] == ['yes', 'yes']
    assert [row['latest'] for row in seen[0]['state']] == [False, True]


@pytest.mark.asyncio
async def test_malformed_response_allows_with_bounded_reason():
    gate, _ = setup_gate({'error': 'private-body'})
    decision = await gate.evaluate(text='hello', history=(), settings=Settings(), api_key='key')
    assert (decision.action, decision.reason) == ('allow', 'invalid_response')


@pytest.mark.asyncio
async def test_hebrew_followup_remains_in_classification_context():
    body = response_body()
    body['answers']['reply_action'].update(choice='ANSWER', probabilities={'ANSWER': .99, 'IGNORE': 0, 'UNCERTAIN': .01})
    gate, seen = setup_gate(body)
    decision = await gate.evaluate(text='כן מחר', history=(Message('assistant', 'לקבוע תזכורת?'),),
                                   settings=Settings.from_mapping({'mode': 'suppress'}), api_key='key')
    assert decision.action == 'allow'
    assert seen[0]['state'][0]['content'] == 'לקבוע תזכורת?'
    assert seen[0]['state'][1]['content'] == 'כן מחר'


def test_engine_does_not_require_host_or_telegram_imports():
    result = subprocess.run([sys.executable, '-c',
        'import sys; import reply_gate.engine; assert not any(k == "telegram" or k.startswith(("gateway.", "hermes_cli.", "agent.")) for k in sys.modules)'],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_attribution_with_unusual_display_name_does_not_leak_sender_id():
    gate, seen = setup_gate()
    decision = await gate.evaluate(text='[Name with ] and | and\nnewline|777888]: hi', history=(),
                        settings=Settings(), api_key='key')
    assert decision.action == 'allow'
    assert seen == []
