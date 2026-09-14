#!/usr/bin/env python3
"""Opt-in R11 after the exact REMOTE R10, never a production migration.

Preserves remote section-owned provenance and priority policy; adds versioned
section persistence, coherent copies, and the local natural-mushroom support fix.
All contracts validate before writes. Existing unversioned decorated worlds fail.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('folia-server/src/minecraft/java')
PROFILE=ROOT/'worldgen-spec/never-nether-r11-hooks.json'
HELPER='net/minecraft/world/level/levelgen/placement/NeverNetherStorageR11.java'


def transform(text: str, rule: dict) -> str:
    def sha(s):return hashlib.sha256(s.encode()).hexdigest()
    changes=rule['replacements']
    if sha(text)==rule['sha256']:
        for item in changes:
            if text.count(item['old'])!=item['count'] or item['new'] in text:
                raise ValueError('Unexpected R11 source anchor')
            text=text.replace(item['old'],item['new'])
        return text
    original=text
    for item in reversed(changes):
        if original.count(item['new'])!=item['count']:raise ValueError('R11 source differs from exact inspected API')
        original=original.replace(item['new'],item['old'])
    if sha(original)!=rule['sha256']:raise ValueError('R11 source does not invert to exact inspected API')
    return text


def prepare(folia:Path)->dict[Path,str]:
    profile=json.loads(PROFILE.read_text())
    if profile['schema']!=1:raise ValueError('Unknown hook schema')
    target=folia/JAVA
    staged={target/rel:transform((target/rel).read_text(),rule) for rel,rule in profile['files'].items()}
    source=ROOT/'qa/nevernether-r11/candidate'
    if {p.relative_to(source).as_posix() for p in source.rglob('*.java')}!={HELPER}:
        raise ValueError('Unexpected R11 helper inventory')
    text=(source/HELPER).read_text()
    if not text.strip():raise ValueError('Empty helper')
    dest=target/HELPER
    if dest.exists() and dest.read_text()!=text:raise ValueError('Different installed helper; use a fresh generated build')
    staged[dest]=text
    return staged


def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folia',type=Path)
    p.add_argument('--acknowledge-experimental-worldgen',action='store_true')
    a=p.parse_args()
    if not a.acknowledge_experimental_worldgen:p.error('Requires explicit opt-in; do not upgrade an existing user world')
    staged=prepare(a.folia)
    for path,text in staged.items():path.write_text(text,encoding='utf-8')
    print(f'NN-R11 section storage experiment installed: {len(staged)} files; lifecycle QA is separate')

if __name__=='__main__':main()
