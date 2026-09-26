#!/usr/bin/env python3
"""Prepare the exact CC0 OpenSimplex2F reference, not code from any mod.

The upstream git blob identities are verified before writing. No floating version
or unverified cache fallback is allowed. The native wrapper supplies a package.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
BLOBS = {
    'OpenSimplex2F.java': '7c9a5320989ebf4b83440b0b029920f7d5fd9933',
    'LICENSE-OpenSimplex2-CC0.txt': '0e259d42c996742e9e3cba14c677129b2c1b6311',
}
CACHE = ROOT / '.work/nevernether-noise-r5'
VENDOR = ROOT / 'third_party/OpenSimplex2'


def verify(payload: bytes, sha: str) -> None:
    digest = hashlib.sha1(b'blob ' + str(len(payload)).encode() + b'\0' + payload).hexdigest()
    if digest != sha:
        raise ValueError(f'OpenSimplex upstream blob mismatch: {digest} != {sha}')


def prepare(cache: Path = CACHE, offline: bool = False) -> dict[str, bytes]:
    staged = {}
    for name, sha in BLOBS.items():
        path = cache / name
        if path.exists():
            payload = path.read_bytes()
        else:
            vendored = VENDOR / name
            if vendored.is_file():
                payload = vendored.read_bytes()
            else:
                if offline:
                    raise ValueError(
                        f'Pinned noise input missing from cache and vendor tree: {path}, {vendored}'
                    )
                url = f'https://api.github.com/repos/KdotJPG/OpenSimplex2/git/blobs/{sha}'
                headers = {'User-Agent': 'NeverFolia-build', 'Accept': 'application/vnd.github+json'}
                token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
                if token:
                    headers['Authorization'] = 'Bearer ' + token
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=30) as response:
                    body = json.load(response)
                if body.get('encoding') != 'base64':
                    raise ValueError('Expected base64 GitHub blob')
                payload = base64.b64decode(body['content'])
        verify(payload, sha)
        staged[name] = payload
    cache.mkdir(parents=True, exist_ok=True)
    for name, payload in staged.items():
        path = cache / name
        if not path.exists():
            path.write_bytes(payload)
    return staged


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache', type=Path, default=CACHE)
    p.add_argument('--offline', action='store_true')
    p.add_argument('--install', type=Path, help='Generated Folia source root')
    args = p.parse_args()
    blobs = prepare(args.cache, args.offline)
    if args.install is not None:
        target = args.install / 'folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/templatesystem/noise/OpenSimplex2F.java'
        license_target = args.install / 'folia-server/src/main/resources/META-INF/licenses/OpenSimplex2-CC0.txt'
        if not (args.install / 'folia-server/src/minecraft/java').is_dir():
            raise ValueError('Generated Folia sources not found')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'package net.minecraft.world.level.levelgen.structure.templatesystem.noise;\n' + blobs['OpenSimplex2F.java'])
        license_target.parent.mkdir(parents=True, exist_ok=True)
        license_target.write_bytes(blobs['LICENSE-OpenSimplex2-CC0.txt'])
    print('[NeverFolia][NN-R5] Verified CC0 OpenSimplex2F inputs: ' + ', '.join(blobs))

if __name__ == '__main__':
    main()
