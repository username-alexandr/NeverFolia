#!/usr/bin/env python3
"""Opt-in R10 substrate experiment, after R8/R9 in a NEW disposable build.

Not installed by the normal production chain. The in-memory substrate is not a
persisted intermediate-chunk format; missing snapshots stop generation, rather
than deriving eligibility from already decorated blocks.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('folia-server/src/minecraft/java')
PROFILE=ROOT/'worldgen-spec/never-nether-r10-hooks.json'
HELPER=Path('net/minecraft/world/level/levelgen/placement/NeverNetherSubstrateR10.java')


def digest(text: str)->str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def transform(text: str, rule: dict)->str:
    replacements=rule['replacements']
    if digest(text)==rule['sha256']:
        for change in replacements:
            old,new,n=change['old'],change['new'],change['count']
            if text.count(old)!=n or new in text:
                raise ValueError('Unexpected source anchor count')
            text=text.replace(old,new)
        return text
    original=text
    for change in reversed(replacements):
        if original.count(change['new'])!=change['count']:
            raise ValueError('Source does not match R10 input or exact output')
        original=original.replace(change['new'],change['old'])
    if digest(original)!=rule['sha256']:
        raise ValueError('R10 output cannot be inverted to its inspected source')
    return text


def prepare(folia: Path)->dict[Path,str]:
    config=json.loads(PROFILE.read_text())
    if config['schema']!=1 or not config['files']:
        raise ValueError('Invalid R10 source contract')
    staged={}
    for name,rule in config['files'].items():
        rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts or not name.startswith('net/minecraft/') or not name.endswith('.java'):
            raise ValueError('Invalid source path')
        dest=folia/JAVA/rel
        staged[dest]=transform(dest.read_text(),rule)
    source=ROOT/'qa/nevernether-r10/candidate'
    if {p.relative_to(source) for p in source.rglob('*.java')}!={HELPER}:
        raise ValueError('Unexpected R10 helper source inventory')
    payload=(source/HELPER).read_text()
    if not payload.strip():raise ValueError('Empty R10 helper')
    dest=folia/JAVA/HELPER
    if dest.exists() and dest.read_text()!=payload:raise ValueError('Different installed R10 helper; use a new build tree')
    staged[dest]=payload
    return staged


def apply(folia: Path)->None:
    staged=prepare(folia)
    for path,text in staged.items():
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,encoding='utf-8')
    print(f'NN-R10 opt-in substrate experiment installed: {len(staged)} source files. No restart/world acceptance implied.')


def main()->None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folia',type=Path)
    parser.add_argument('--acknowledge-experimental-worldgen',action='store_true')
    args=parser.parse_args()
    if not args.acknowledge_experimental_worldgen:parser.error('Requires explicit opt-in; never update an existing world with this experiment')
    apply(args.folia)

if __name__=='__main__':main()
