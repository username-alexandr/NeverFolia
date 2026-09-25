#!/usr/bin/env python3
"""Install NeverOverworld FIELD-R11 after final FIELD-R10.

The change is owner-chunk-only and new-world-only. It adds one deterministic
boundary-component flood pass immediately before drowned-surface weathering, so
the existing weather/cleanup sees the newly flooded shallow volume. The script
is exact-source, atomic and idempotent; it never edits an existing world.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('folia-server/src/minecraft/java')
FLOOD=Path('net/minecraft/world/level/chunk/NeverOverworldFlood.java')
HELPER=Path('net/minecraft/world/level/chunk/NeverOverworldFloodBoundaryR11.java')
SOURCE_ROOT=ROOT/'native/neveroverworld/field-r11/java'
EXPECTED_FLOOD_SHA='f8a95bb7349b0f44f7babb138c2e5caa9f0366c29d9a58bee43231570a5a3ce6'
ANCHOR='        weatherSubmergedSurface(chunk, minY, FLOOD_LEVEL);\n'
CALL='        NeverOverworldFloodBoundaryR11.apply(level, chunk);\n'+ANCHOR


def sha(text:str)->str:return hashlib.sha256(text.encode()).hexdigest()

def helper_source()->str:
    path=SOURCE_ROOT/HELPER
    if not path.is_file():raise ValueError('FIELD-R11 helper missing: '+str(path))
    text=path.read_text()
    if not text.strip():raise ValueError('FIELD-R11 helper empty')
    return text

def patch_flood(text:str)->str:
    if CALL in text:
        if text.count(CALL)!=1:raise ValueError('Duplicate FIELD-R11 flood call')
        original=text.replace(CALL,ANCHOR,1)
        if sha(original)!=EXPECTED_FLOOD_SHA:raise ValueError('Installed FIELD-R11 flood does not invert to exact FIELD-R10 source')
        return text
    if sha(text)!=EXPECTED_FLOOD_SHA:raise ValueError('NeverOverworldFlood differs from inspected final FIELD-R10 source')
    if text.count(ANCHOR)!=1:raise ValueError('Expected one drowned-surface weathering anchor')
    out=text.replace(ANCHOR,CALL,1)
    if out.count('NeverOverworldFloodBoundaryR11.apply(level, chunk);')!=1:raise ValueError('FIELD-R11 call installation failed')
    return out

def prepare(folia:Path)->dict[Path,str]:
    root=folia/JAVA; flood=root/FLOOD
    if not flood.is_file():raise ValueError('Materialized NeverOverworldFlood missing')
    helper=helper_source();dest=root/HELPER
    if dest.exists() and dest.read_text()!=helper:raise ValueError('Conflicting FIELD-R11 helper; use fresh generated sources')
    return {flood:patch_flood(flood.read_text()),dest:helper}

def apply(folia:Path)->None:
    staged=prepare(folia)
    for path,text in staged.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
    print('[NeverFolia][NeverOverworld FIELD-R11] shallow boundary flood continuity installed before drowned-surface weathering')

def main()->None:
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folia',type=Path);p.add_argument('--check-only',action='store_true');a=p.parse_args()
    staged=prepare(a.folia)
    if a.check_only:print(f'[NeverFolia][NeverOverworld FIELD-R11] preflight OK: {len(staged)} files; no writes');return
    apply(a.folia)
if __name__=='__main__':main()
