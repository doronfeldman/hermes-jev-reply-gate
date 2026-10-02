"""Strict configuration with conservative, inert defaults."""
from collections.abc import Mapping
from dataclasses import dataclass, fields
import math
import re


@dataclass(frozen=True)
class Settings:
    enabled: bool = False
    mode: str = 'shadow'
    model: str = 'jev-1.13.0'
    timeout_seconds: float = 1.0
    ignore_probability: float = .95
    context_messages: int = 12
    context_characters: int = 6000
    max_sessions: int = 128
    group_ids: frozenset[str] = frozenset()

    @classmethod
    def from_mapping(cls, value):
        allowed = {field.name for field in fields(cls)} - {'group_ids'} | {'telegram'}
        if not isinstance(value, Mapping) or set(value) - allowed:
            raise ValueError('Invalid reply-gate settings')
        defaults = cls()
        values = {name: value.get(name, getattr(defaults, name)) for name in allowed - {'telegram'}}
        if type(values['enabled']) is not bool:
            raise ValueError('enabled must be boolean')
        if values['mode'] not in ('shadow', 'suppress'):
            raise ValueError('mode must be shadow or suppress')
        if values['model'] != defaults.model:
            raise ValueError('Only the pinned Jev model is supported')
        for name in ('context_messages', 'context_characters', 'max_sessions'):
            if type(values[name]) is not int or values[name] <= 0:
                raise ValueError(f'{name} must be a positive integer')
        for name in ('timeout_seconds', 'ignore_probability'):
            number = values[name]
            if type(number) not in (int, float) or not math.isfinite(number):
                raise ValueError(f'{name} must be finite and numeric')
        if values['timeout_seconds'] <= 0:
            raise ValueError('timeout_seconds must be positive')
        if not .5 < values['ignore_probability'] <= 1:
            raise ValueError('ignore_probability must be in (0.5, 1]')
        telegram = value.get('telegram', {})
        if not isinstance(telegram, Mapping) or set(telegram) - {'group_ids'}:
            raise ValueError('Invalid telegram settings')
        groups = telegram.get('group_ids', [])
        if not isinstance(groups, (list, tuple)) or any(
            type(group) not in (int, str) or not re.fullmatch(r'-?[0-9]+', str(group))
            for group in groups
        ):
            raise ValueError('telegram.group_ids must contain numeric group IDs')
        return cls(**values, group_ids=frozenset(str(group) for group in groups))
