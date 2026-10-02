"""Pure reply policy over an authoritative, prior-message-only snapshot."""
from dataclasses import dataclass
import re

from .config import Settings
from .jev import Classification, JevClient, JevError

ATTRIBUTION = re.compile(r'\[([^\]\n|]*)\|([^\]\n|]+)\]')


@dataclass(frozen=True)
class GateDecision:
    action: str
    reason: str
    classification: Classification | None = None


def project_context(text, history, settings):
    """Retain a complete suffix; pseudonyms last for exactly one request.

    The host excludes the current event from history. Identical text from two
    different events is deliberately preserved. Only host attribution syntax is
    pseudonymized; this is not general personal-data removal from message bodies.
    """
    limit = min(settings.context_characters, 6000)
    if not text.strip() or len(text) > limit:
        return None
    selected = [(entry.role, entry.content) for entry in history
                if entry.role in ('user', 'assistant') and isinstance(entry.content, str)]
    selected.append(('user', text))
    recent = []
    remaining = limit
    for role, content in reversed(selected):
        if len(recent) >= min(settings.context_messages, 12) or len(content) > remaining:
            break
        recent.append((role, content))
        remaining -= len(content)
    aliases = {}
    def alias(match):
        identity = match.group(2)
        if identity not in aliases:
            aliases[identity] = f'Speaker {len(aliases) + 1}'
        return aliases[identity]
    state = [{'role': role, 'content': ATTRIBUTION.sub(alias, content), 'latest': False}
             for role, content in reversed(recent)]
    # Ambiguous/malformed attribution must not leak the raw identity or remove
    # conversational instructions via an overly greedy redaction expression.
    if any(re.search(r'\|[^\]\n]+\]', row['content']) for row in state):
        return None
    if not state or sum(len(row['content']) for row in state) > limit:
        return None
    state[-1]['latest'] = True
    return state


class ReplyGate:
    def __init__(self, client: JevClient | None = None):
        self.client = client or JevClient()

    async def evaluate(self, *, text, history, settings: Settings, api_key: str) -> GateDecision:
        state = project_context(text, history, settings)
        if state is None:
            return GateDecision('allow', 'context_budget')
        try:
            answer = await self.client.classify(state, api_key=api_key, timeout_seconds=settings.timeout_seconds)
        except JevError as error:
            return GateDecision('allow', str(error))
        if answer.choice != 'IGNORE':
            return GateDecision('allow', answer.choice.lower(), answer)
        if answer.probabilities['IGNORE'] < settings.ignore_probability:
            return GateDecision('allow', 'below_threshold', answer)
        if settings.mode == 'shadow':
            return GateDecision('allow', 'would_ignore', answer)
        return GateDecision('observe', 'confident_ignore', answer)
