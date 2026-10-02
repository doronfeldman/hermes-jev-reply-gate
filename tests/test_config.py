import pytest

from reply_gate.config import Settings


def test_defaults_are_inert():
    settings = Settings.from_mapping({})
    assert settings.enabled is False
    assert settings.mode == 'shadow'
    assert settings.group_ids == frozenset()
    assert settings.model == 'jev-1.13.0'
    assert settings.timeout_seconds == 1.0
    assert settings.ignore_probability == .95
    assert (settings.context_messages, settings.context_characters, settings.max_sessions) == (12, 6000, 128)


def test_group_ids_normalized_and_settings_immutable():
    settings = Settings.from_mapping({'telegram': {'group_ids': [-100123, '-100456']}})
    assert settings.group_ids == frozenset({'-100123', '-100456'})
    with pytest.raises(AttributeError):
        settings.enabled = True


@pytest.mark.parametrize('mapping', [
    None, [], {'enabled': 1}, {'enabled': 'true'}, {'mode': 'active'},
    {'mode': []}, {'model': 'jev-latest'}, {'context_messages': True},
    {'context_characters': 0}, {'max_sessions': -1}, {'context_messages': 1.5},
    {'timeout_seconds': True}, {'timeout_seconds': 0}, {'timeout_seconds': float('nan')},
    {'timeout_seconds': float('inf')}, {'ignore_probability': .5},
    {'ignore_probability': 1.01}, {'ignore_probability': float('nan')},
    {'telegram': []}, {'telegram': {'group_ids': '123'}},
    {'telegram': {'group_ids': [True]}}, {'telegram': {'group_ids': ['']}},
    {'telegram': {'group_ids': [1.5]}}, {'telegram': {'group_ids': ['name']}},
    {'telegram': {'wrong': 1}}, {'api_key': 'never-a-setting'}, {'enabeld': True},
])
def test_invalid_settings_rejected_without_echoing_values(mapping):
    with pytest.raises(ValueError) as error:
        Settings.from_mapping(mapping)
    assert 'never-a-setting' not in str(error.value)


def test_threshold_upper_boundary_is_valid():
    assert Settings.from_mapping({'ignore_probability': 1}).ignore_probability == 1


def test_model_version_uses_a_host_allowed_plugin_relative_key():
    assert Settings.from_mapping({'model_version': 'jev-1.13.0'}).model == 'jev-1.13.0'
    with pytest.raises(ValueError):
        Settings.from_mapping({'model_version': 'jev-latest'})
