#!/usr/bin/env python3
"""Exact-source R14 logical roof512, after the inspected R8-R13 chain.

No existing world is rewritten. This requires the separate matching R14 data pack.
All source hashes, occurrence counts and helper conflicts are checked before writes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('folia-server/src/minecraft/java')
PROFILE=ROOT/'worldgen-spec/never-nether-r14-hooks.json'
HELPER=Path('net/minecraft/world/level/levelgen/placement/NeverNetherHeightR14.java')


def sha(text):return hashlib.sha256(text.encode()).hexdigest()


def transform(name,text,contract):
    if sha(text)==contract['sha256']:
        for item in contract['replacements']:
            if text.count(item['old'])!=item['count'] or item['new'] in text:raise ValueError('Unexpected height hook count: '+name)
            text=text.replace(item['old'],item['new'])
        return text
    original=text
    for item in reversed(contract['replacements']):
        if original.count(item['new'])!=item['count']:raise ValueError('Height input identity mismatch: '+name)
        original=original.replace(item['new'],item['old'])
    if sha(original)!=contract['sha256']:raise ValueError('Installed height hooks fail exact inversion: '+name)
    return text


def prepare(folia):
    profile=json.loads(PROFILE.read_text());target=folia/JAVA
    staged={target/name:transform(name,(target/name).read_text(),rules) for name,rules in profile['files'].items()}
    text=(ROOT/'qa/nevernether-r14/candidate'/HELPER).read_text()
    if not text.strip():raise ValueError('Missing height helper')
    dest=target/HELPER
    if dest.exists() and dest.read_text()!=text:raise ValueError('Conflicting height helper; use fresh generated sources')
    staged[dest]=text
    return staged


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folia',type=Path);p.add_argument('--acknowledge-experimental-worldgen',action='store_true')
    a=p.parse_args()
    if not a.acknowledge_experimental_worldgen:p.error('Explicit new-world height profile acknowledgement required')
    staged=prepare(a.folia)
    for path,text in staged.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    print(f'R14 roof512 installed: {len(staged)} source files; requires matching new-world data pack. World acceptance remains separate.')
if __name__=='__main__':main()
