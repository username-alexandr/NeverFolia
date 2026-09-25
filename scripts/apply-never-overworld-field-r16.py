#!/usr/bin/env python3
"""FIELD-R16: local village-piece foundation repair after VILLAGE-NOFILL.

Adds a bounded post-placement foundation pass for village pieces only. It never
restores whole-village reclamation and never fills to ocean level.
"""
from __future__ import annotations
import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('folia-server/src/minecraft/java')
STRUCT=JAVA/'net/minecraft/world/level/levelgen/structure/StructureStart.java'
HELPER_SRC=ROOT/'native/neveroverworld/field-r16/java/net/minecraft/world/level/levelgen/structure/NeverOverworldVillageFoundationR16.java'
HELPER_DST=JAVA/'net/minecraft/world/level/levelgen/structure/NeverOverworldVillageFoundationR16.java'
ANCHOR='            // VILLAGE-NOFILL-R1: keep vanilla placement; never reclaim the surrounding ocean to Y=128.\n'
CALL='            NeverOverworldVillageFoundationR16.apply(level, this, chunkPos);\n'

def patch(text:str)->str:
    if CALL in text:return text
    if text.count(ANCHOR)!=1:raise ValueError('FIELD-R16 VILLAGE-NOFILL anchor mismatch')
    return text.replace(ANCHOR,ANCHOR+CALL,1)

def prepare(folia:Path):
    s=folia/STRUCT
    if not s.is_file():raise ValueError('StructureStart missing')
    payload=HELPER_SRC.read_text()
    dst=folia/HELPER_DST
    if dst.exists() and dst.read_text()!=payload:raise ValueError('Conflicting FIELD-R16 helper')
    return {s:patch(s.read_text()),dst:payload}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folia',type=Path);p.add_argument('--check-only',action='store_true');a=p.parse_args()
    staged=prepare(a.folia.resolve())
    if not a.check_only:
        for path,text in staged.items():
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    print('[FIELD-R16] local village-piece foundations '+('preflight' if a.check_only else 'installed'))

if __name__=='__main__':main()
