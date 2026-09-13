#!/usr/bin/env python3
"""Fetch original pinned upstream loot separately from user source ZIPs."""
from __future__ import annotations
import argparse
import base64
import json
from pathlib import Path
import urllib.request
from nevernether_monument_r5 import PROFILE, CACHE, blob_hash, read_supplements


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=CACHE)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    profile = json.loads(PROFILE.read_text())
    pending = {}
    for item in profile['supplemental_files']:
        path = args.cache / item['filename']
        if path.exists():
            raw = path.read_bytes()
        else:
            if args.offline:
                raise SystemExit(f'Missing pinned loot cache: {path}')
            url = f"https://api.github.com/repos/TelepathicGrunt/RepurposedStructures/git/blobs/{item['git_blob']}"
            request = urllib.request.Request(url, headers={'User-Agent': 'NeverFolia-build'})
            with urllib.request.urlopen(request, timeout=30) as response:
                value = json.load(response)
            if value.get('encoding') != 'base64':
                raise SystemExit('Invalid upstream encoding')
            raw = base64.b64decode(value['content'])
        if blob_hash(raw) != item['git_blob']:
            raise SystemExit(f'Pinned upstream loot mismatch: {path.name}')
        pending[path] = raw
    args.cache.mkdir(parents=True, exist_ok=True)
    for path, raw in pending.items():
        if not path.exists():
            path.write_bytes(raw)
    read_supplements(args.cache, profile)
    print('Original monument loot verified; source ZIPs unchanged')

if __name__ == '__main__':
    main()
