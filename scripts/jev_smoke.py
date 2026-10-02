"""Explicitly paid, three-request API contract smoke check using synthetic text."""
import argparse
import asyncio
import os
import sys
import time

from reply_gate.jev import JevClient, JevError

CASES = (
    ('chatter', [{'role': 'user', 'content': 'Speaker 1: I just got home.'}]),
    ('request', [{'role': 'user', 'content': 'Speaker 1: Hermes, help me plan dinner.'}]),
    ('hebrew', [{'role': 'user', 'content': 'Speaker 1: הרגע הגעתי הביתה'}]),
)


async def probe(api_key, *, client=None):
    client = client or JevClient()
    for name, state in CASES:
        start = time.perf_counter()
        result = await client.classify(state, api_key=api_key, timeout_seconds=5.0)
        # Client validation proves the API contract; this tiny sample cannot prove accuracy.
        print(f'{name}: {result.choice}, {time.perf_counter() - start:.3f}s')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true', required=True,
                        help='authorize up to three billable Jev API requests')
    parser.parse_args()
    key = os.environ.get('TYPESAFE_API_KEY', '').strip()
    if not key:
        print('TYPESAFE_API_KEY is required', file=sys.stderr)
        return 2
    try:
        asyncio.run(probe(key))
    except JevError as error:
        # JevError has bounded categories only; never print requests or credentials.
        print(f'Jev smoke failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
