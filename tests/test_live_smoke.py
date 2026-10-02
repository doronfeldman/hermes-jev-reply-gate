"""The paid smoke probe must remain opt-in and have bounded request count."""
import importlib.util
from pathlib import Path
import subprocess
import sys

import httpx
import pytest

from test_jev import response_body

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'jev_smoke.py'


def test_smoke_requires_explicit_flag_even_with_key():
    result = subprocess.run([sys.executable, str(SCRIPT)],
                            env={'TYPESAFE_API_KEY': 'synthetic-key'}, capture_output=True)
    assert result.returncode == 2
    assert b'--live' in result.stderr
    assert b'synthetic-key' not in result.stderr


def test_smoke_without_key_fails_without_network():
    result = subprocess.run([sys.executable, str(SCRIPT), '--live'],
                            env={}, capture_output=True)
    assert result.returncode == 2
    assert b'TYPESAFE_API_KEY is required' in result.stderr


@pytest.mark.asyncio
async def test_smoke_makes_exactly_three_synthetic_requests():
    spec = importlib.util.spec_from_file_location('jev_smoke', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from reply_gate.jev import JevClient
    seen = []

    def serve(request):
        seen.append(request)
        return httpx.Response(200, json=response_body())

    await module.probe('synthetic-key', client=JevClient(transport=httpx.MockTransport(serve)))
    assert len(seen) == 3
    assert all(r.url == 'https://api.typesafe.ai/v1/systemone' for r in seen)
