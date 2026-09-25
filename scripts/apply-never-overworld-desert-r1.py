#!/usr/bin/env python3
"""Install NeverOverworld DESERT-R1 after FIELD-R11.

Adds rare owning-chunk oases/palms after flood cleanup and a ServerPlayer desert
sandstorm tick. No overheating mechanic. Exact-source, atomic and idempotent.
"""
from __future__ import annotations
import argparse,hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('folia-server/src/minecraft/java')
FLOOD=Path('net/minecraft/world/level/chunk/NeverOverworldFlood.java')
PLAYER=Path('net/minecraft/server/level/ServerPlayer.java')
OASIS=Path('net/minecraft/world/level/chunk/NeverOverworldDesertR1.java')
STORM=Path('net/minecraft/server/level/NeverOverworldSandstormR1.java')
SRC=ROOT/'native/neveroverworld/desert-r1/java'
FIELD_R11_FLOOD_SHA='d16b976c80533ad78e77d35f59fcd2ae2ece3fcef34266ecaab0b21ac22106c9'
SERVER_PLAYER_SHA='3d1702fcbccb52330c13937a1beff6bf827c2ed651a797a9580ec88375a6d1f3'
FLOOD_ANCHOR='        NeverOverworldSubmergedRemnants.apply(level, chunk);\n'
FLOOD_CALL=FLOOD_ANCHOR+'        NeverOverworldDesertR1.generate(level, chunk);\n'
PLAYER_ANCHOR='''        this.updatePlayerAttributes();
        this.advancements.flushDirty(this, true);
'''
PLAYER_CALL='''        this.updatePlayerAttributes();
        NeverOverworldSandstormR1.tick(this);
        this.advancements.flushDirty(this, true);
'''

def sha(s:str)->str:return hashlib.sha256(s.encode()).hexdigest()
def canonical(rel:Path)->str:
    p=SRC/rel
    if not p.is_file():raise ValueError('missing DESERT-R1 source '+str(p))
    v=p.read_text()
    if not v.strip():raise ValueError('empty DESERT-R1 source '+str(p))
    return v

def patch_flood(s:str)->str:
    if FLOOD_CALL in s:
        if s.count(FLOOD_CALL)!=1:raise ValueError('duplicate DESERT-R1 oasis call')
        original=s.replace(FLOOD_CALL,FLOOD_ANCHOR,1)
        if sha(original)!=FIELD_R11_FLOOD_SHA:raise ValueError('installed oasis call does not invert to FIELD-R11')
        return s
    if sha(s)!=FIELD_R11_FLOOD_SHA:raise ValueError('NeverOverworldFlood is not exact FIELD-R11 output')
    if s.count(FLOOD_ANCHOR)!=1:raise ValueError('submerged-remnant anchor drifted')
    return s.replace(FLOOD_ANCHOR,FLOOD_CALL,1)

def patch_player(s:str)->str:
    if PLAYER_CALL in s:
        if s.count(PLAYER_CALL)!=1:raise ValueError('duplicate DESERT-R1 player tick')
        original=s.replace(PLAYER_CALL,PLAYER_ANCHOR,1)
        if sha(original)!=SERVER_PLAYER_SHA:raise ValueError('installed player hook does not invert to inspected source')
        return s
    if sha(s)!=SERVER_PLAYER_SHA:raise ValueError('ServerPlayer source identity changed')
    if s.count(PLAYER_ANCHOR)!=1:raise ValueError('ServerPlayer tick anchor drifted')
    return s.replace(PLAYER_ANCHOR,PLAYER_CALL,1)

def prepare(folia:Path)->dict[Path,str]:
    root=folia/JAVA
    flood=root/FLOOD;player=root/PLAYER
    if not flood.is_file() or not player.is_file():raise ValueError('materialized flood/player sources missing')
    staged={flood:patch_flood(flood.read_text()),player:patch_player(player.read_text())}
    for rel in (OASIS,STORM):
        dest=root/rel;src=canonical(rel)
        if dest.exists() and dest.read_text()!=src:raise ValueError('conflicting DESERT-R1 helper '+str(dest))
        staged[dest]=src
    return staged

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folia',type=Path);p.add_argument('--check-only',action='store_true');a=p.parse_args()
    staged=prepare(a.folia)
    if a.check_only:
        print(f'[NeverFolia][DESERT-R1] preflight OK: {len(staged)} files; no writes')
        return
    for path,text in staged.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    print('[NeverFolia][DESERT-R1] rare oases/palms + wind sandstorms installed; overheating disabled')

if __name__=='__main__':main()
