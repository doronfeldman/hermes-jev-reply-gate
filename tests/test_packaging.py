import os
from pathlib import Path
import subprocess
import sys
import zipfile


def test_built_wheel_entrypoint_imports_outside_checkout_and_refuses_old_host(tmp_path):
    root = Path(__file__).resolve().parents[1]
    wheel_dir = tmp_path / 'wheels'
    wheel_dir.mkdir()
    result = subprocess.run([sys.executable, '-c',
        'import setuptools.build_meta as backend; import sys; backend.build_wheel(sys.argv[1])', str(wheel_dir)],
        cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    wheel, = wheel_dir.glob('*.whl')
    installed = tmp_path / 'installed'
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(installed)
    script = '''
import importlib.metadata
import sys
sys.path.insert(0, sys.argv[1])
dist, = importlib.metadata.distributions(path=[sys.argv[1]])
entry, = [ep for ep in dist.entry_points if ep.group == 'hermes_agent.plugins']
assert entry.name == 'hermes-jev-reply-gate'
register = entry.load()
try:
    register(object())
except RuntimeError as error:
    assert 'register_ingress_policy' in str(error)
else:
    raise AssertionError('old host must be refused')
'''
    result = subprocess.run([sys.executable, '-I', '-c', script, str(installed)],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
