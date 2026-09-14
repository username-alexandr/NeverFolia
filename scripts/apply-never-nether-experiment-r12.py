#!/usr/bin/env python3
"""Optional R12 after exact R11: deterministic decoration proposals, new policy ID.

Never invoked by the normal production chain. All source hashes, hook counts and
helper conflicts validate before writes. No existing-world metadata migration.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('folia-server/src/minecraft/java')
PROFILE=ROOT/'worldgen-spec/never-nether-r12-hooks.json'
HELPERS=('net/minecraft/world/level/levelgen/placement/NeverNetherProposalR12.java',)


def transform(text: str,rule: dict)->str:
    def sha(s):return hashlib.sha256(s.encode()).hexdigest()
    if sha(text)==rule['sha256']:
        for item in rule['replacements']:
            if text.count(item['old'])!=item['count'] or item['new'] in text:
                raise ValueError('Unexpected R12 source hook')
            text=text.replace(item['old'],item['new'])
        return text
    original=text
    for item in reversed(rule['replacements']):
        if original.count(item['new'])!=item['count']:
            raise ValueError('R12 source identity mismatch')
        original=original.replace(item['new'],item['old'])
    if sha(original)!=rule['sha256']:
        raise ValueError('R12 source cannot invert to exact inspected R11')
    return text


def prepare(folia:Path)->dict[Path,str]:
    profile=json.loads(PROFILE.read_text())
    if profile['schema']!=1:raise ValueError('Unsupported hook schema')
    target=folia/JAVA
    staged={target/name:transform((target/name).read_text(),rule) for name,rule in profile['files'].items()}
    source=ROOT/'qa/nevernether-r12/candidate'
    if {p.relative_to(source).as_posix() for p in source.rglob('*.java')}!=set(HELPERS):
        raise ValueError('Unexpected candidate helper inventory')
    for name in HELPERS:
        text=(source/name).read_text()
        if not text.strip():raise ValueError('Empty R12 helper')
        dest=target/name
        if dest.exists() and dest.read_text()!=text:raise ValueError('Conflicting helper; use a fresh build')
        staged[dest]=text
    return staged


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folia',type=Path)
    parser.add_argument('--acknowledge-experimental-worldgen',action='store_true')
    args=parser.parse_args()
    if not args.acknowledge_experimental_worldgen:parser.error('Explicit opt-in required; existing worlds must not be upgraded')
    staged=prepare(args.folia)
    for path,text in staged.items():path.write_text(text,encoding='utf-8')
    print(f'R12 optional proposal policy installed: {len(staged)} sources; new metadata profile, world acceptance separate')

if __name__=='__main__':main()
