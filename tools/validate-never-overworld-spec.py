#!/usr/bin/env python3
import json
from pathlib import Path

SPEC = Path('worldgen-spec/never-overworld.json')


def fail(message):
    raise SystemExit(f'[FAIL] {message}')


def main():
    if not SPEC.exists():
        fail('missing never-overworld.json')

    data = json.loads(SPEC.read_text(encoding='utf-8'))

    dim = data.get('dimension', {})
    if dim.get('min_y') != -512:
        fail('invalid min_y')
    if dim.get('height') != 1024:
        fail('invalid height')
    if dim.get('max_y') != 511:
        fail('invalid max_y')

    policies = data.get('policies', {})
    if policies.get('chunk_order_independent') is not True:
        fail('determinism policy disabled')

    if policies.get('lava_aquifer') != 'disabled':
        fail('lava aquifer policy missing')

    print('[OK] NeverOverworld specification validated')


if __name__ == '__main__':
    main()
