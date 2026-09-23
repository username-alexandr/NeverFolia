#!/usr/bin/env python3
"""FIELD-R15: final verified-ocean flood audit and flooded-cave ecology cleanup.

Install after FIELD-R14. Replaces the R14 boundary-only continuation with a scan
of every floodable component through Y=128. Only components that already contain
verified ocean water are filled. Lava-adjacent and dry-mine cells remain hard
barriers. Then remove cave vines/azalea/dripleaf from flooded cave cells and
remove cactus/melon/oxeye daisy at or below the Y=128 ocean plane. Oxeye daisy is also height-gated before SimpleBlockFeature placement.
"""
from __future__ import annotations
import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('folia-server/src/minecraft/java')
FLOOD=JAVA/'net/minecraft/world/level/chunk/NeverOverworldFlood.java'
FLOOD15_SRC=ROOT/'native/neveroverworld/field-r15/java/net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java'
FLOOD15_DST=JAVA/'net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java'
ECO15_SRC=ROOT/'native/neveroverworld/field-r15/java/net/minecraft/world/level/chunk/NeverOverworldEcologyR15.java'
ECO15_DST=JAVA/'net/minecraft/world/level/chunk/NeverOverworldEcologyR15.java'
SIMPLE=JAVA/'net/minecraft/world/level/levelgen/feature/SimpleBlockFeature.java'
BAMBOO=JAVA/'net/minecraft/world/level/levelgen/feature/BambooFeature.java'

OLD='        NeverOverworldFloodConnectivityR14.apply(level, chunk);'
NEW='        NeverOverworldEcologyR15.cleanup(level, chunk);\n        NeverOverworldFloodConnectivityR15.apply(level, chunk);'
ECO_ANCHOR='        NeverOverworldEcologyR13.cleanup(level, chunk);'
ECO_NEW=ECO_ANCHOR+'\n        NeverOverworldEcologyR15.cleanup(level, chunk);'
SIMPLE_ANCHOR='        if (!net.minecraft.world.level.chunk.NeverOverworldEcologyR13.allowSimpleBlock(level, origin, stateToPlace)) return false;'
SIMPLE_NEW=SIMPLE_ANCHOR+'\n        if (!net.minecraft.world.level.chunk.NeverOverworldEcologyR15.allowSimpleBlock(level, origin, stateToPlace)) return false;'
BAMBOO_ANCHOR='        if (!net.minecraft.world.level.chunk.NeverOverworldEcologyR13.allowHeightGatedOrigin(level, origin)) return false;'
BAMBOO_NEW=BAMBOO_ANCHOR+'\n        if (!net.minecraft.world.level.chunk.NeverOverworldEcologyR15.allowOceanHeightOrigin(level, origin)) return false;'

def patch(text:str)->str:
    if 'NeverOverworldFloodConnectivityR15.apply(level, chunk);' in text and text.count('NeverOverworldEcologyR15.cleanup(level, chunk);') >= 2:
        return text
    if text.count(OLD)!=1: raise ValueError('FIELD-R15 R14 flood-call anchor mismatch')
    if text.count(ECO_ANCHOR)!=1: raise ValueError('FIELD-R15 ecology anchor mismatch')
    text=text.replace(OLD,NEW,1)
    text=text.replace(ECO_ANCHOR,ECO_NEW,1)
    return text

def patch_simple(text:str)->str:
    if 'NeverOverworldEcologyR15.allowSimpleBlock(level, origin, stateToPlace)' in text:
        return text
    if text.count(SIMPLE_ANCHOR)!=1: raise ValueError('FIELD-R15 SimpleBlockFeature anchor mismatch')
    return text.replace(SIMPLE_ANCHOR,SIMPLE_NEW,1)

def patch_bamboo(text:str)->str:
    if 'NeverOverworldEcologyR15.allowOceanHeightOrigin(level, origin)' in text:
        return text
    if text.count(BAMBOO_ANCHOR)!=1: raise ValueError('FIELD-R15 BambooFeature anchor mismatch')
    return text.replace(BAMBOO_ANCHOR,BAMBOO_NEW,1)

def prepare(folia:Path):
    flood=folia/FLOOD
    simple=folia/SIMPLE
    bamboo=folia/BAMBOO
    if not flood.is_file(): raise ValueError('NeverOverworldFlood missing')
    if not simple.is_file(): raise ValueError('SimpleBlockFeature missing')
    if not bamboo.is_file(): raise ValueError('BambooFeature missing')
    staged={flood:patch(flood.read_text()),simple:patch_simple(simple.read_text()),bamboo:patch_bamboo(bamboo.read_text())}
    for src,dst in ((FLOOD15_SRC,FLOOD15_DST),(ECO15_SRC,ECO15_DST)):
        payload=src.read_text()
        target=folia/dst
        if target.exists() and target.read_text()!=payload: raise ValueError('Conflicting FIELD-R15 helper: '+str(dst))
        staged[target]=payload
    return staged

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folia',type=Path);p.add_argument('--check-only',action='store_true');a=p.parse_args()
    staged=prepare(a.folia.resolve())
    if not a.check_only:
        for path,text in staged.items():
            path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    print('[FIELD-R15] full verified-water audit Y<=128 + flooded cave flora cleanup + cactus/melon/oxeye-daisy height gate '+('preflight' if a.check_only else 'installed'))

if __name__=='__main__':main()
