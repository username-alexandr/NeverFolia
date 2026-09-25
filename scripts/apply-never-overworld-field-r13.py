#!/usr/bin/env python3
"""FIELD-R13: flooded flora/fluids and post-boundary dry-mine hardening.

Install after FIELD-R12 and ORE-LIGHT-R12. Exact inspected sources only.
"""
from __future__ import annotations
import argparse,hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('folia-server/src/minecraft/java')
HELPER_SRC=ROOT/'native/neveroverworld/field-r13/java/net/minecraft/world/level/chunk/NeverOverworldEcologyR13.java'
CONTRACTS={
 'net/minecraft/world/level/chunk/NeverOverworldFlood.java':('e53f50c7894e8e5f86f5237cdc20da08a83efc002e312313c12da60e3301017e','febbcb5a282083aab04bbd09e966f47d7a99fc265f8b80113055b1df85541330'),
 'net/minecraft/world/level/levelgen/feature/AbstractHugeMushroomFeature.java':('a4cf4f88989763db1e17d43a4d8d62fd9465e4487ded20b8fb9d4c4380a14064','3e4928b5c8698b5b080916db0272beeedb90d3e9fff07ff618f831b43b67d0ae'),
 'net/minecraft/world/level/levelgen/feature/BambooFeature.java':('66adda38a84734b7fe58df101259d073cc5f5fffe2db6e01252ba6aa92075efc','7516074f9993879c9f48abe45b0ee6dd1d64a41d0d128a0e27ea55a0b73d56e1'),
 'net/minecraft/world/level/levelgen/feature/SimpleBlockFeature.java':('b7c379cfbfb7e5ad77cadadbeedf7f019550dc7f11caed746230fe97ac482ccf','96491646ad987a0a65faaa2da5d55d7c3a780e16346eb26f950961f49e63a592'),
}
RULES={
 'net/minecraft/world/level/chunk/NeverOverworldFlood.java':[
  ('        final FloodShorelineSnapshot shorelineFlora = captureFloodShorelineFlora(chunk);',
   '        // FIELD-R13: erase generated underground fluids before rebuilding only the surface-connected ocean.\n        removeGeneratedFluids(chunk, minY, FLOOD_LEVEL, air);\n        final FloodShorelineSnapshot shorelineFlora = captureFloodShorelineFlora(chunk);'),
  ('        NeverOverworldFloodBoundaryR11.apply(level, chunk);\n        weatherSubmergedSurface(chunk, minY, FLOOD_LEVEL);',
   '        NeverOverworldFloodBoundaryR11.apply(level, chunk);\n        // Re-drain protected mine pieces after every flood pass; generation-only, pre-FULL.\n        NeverOverworldDryMinesR12.prepare(chunk);\n        NeverOverworldEcologyR13.cleanup(level, chunk);\n        weatherSubmergedSurface(chunk, minY, FLOOD_LEVEL);')],
 'net/minecraft/world/level/levelgen/feature/AbstractHugeMushroomFeature.java':[
  ('        BlockPos origin = context.origin();\n        RandomSource random = context.random();',
   '        BlockPos origin = context.origin();\n        if (!net.minecraft.world.level.chunk.NeverOverworldEcologyR13.allowHeightGatedOrigin(level, origin)) return false;\n        RandomSource random = context.random();')],
 'net/minecraft/world/level/levelgen/feature/BambooFeature.java':[
  ('        BlockPos origin = context.origin();\n        WorldGenLevel level = context.level();',
   '        BlockPos origin = context.origin();\n        WorldGenLevel level = context.level();\n        if (!net.minecraft.world.level.chunk.NeverOverworldEcologyR13.allowHeightGatedOrigin(level, origin)) return false;')],
 'net/minecraft/world/level/levelgen/feature/SimpleBlockFeature.java':[
  ('        if (stateToPlace == null) {\n            return false;\n        }\n\n        if (stateToPlace.canSurvive(level, origin)) {',
   '        if (stateToPlace == null) {\n            return false;\n        }\n        if (!net.minecraft.world.level.chunk.NeverOverworldEcologyR13.allowSimpleBlock(level, origin, stateToPlace)) return false;\n\n        if (stateToPlace.canSurvive(level, origin)) {')],
}

def sha(s): return hashlib.sha256(s.encode()).hexdigest()

def transform(rel,text):
    before,after=CONTRACTS[rel]
    if sha(text)==after:return text
    if sha(text)!=before:raise ValueError('Uninspected FIELD-R13 input: '+rel+' '+sha(text))
    for old,new in RULES[rel]:
        if text.count(old)!=1:raise ValueError('FIELD-R13 anchor drift: '+rel)
        text=text.replace(old,new,1)
    if sha(text)!=after:raise ValueError('FIELD-R13 output drift: '+rel+' '+sha(text))
    return text

def prepare(folia):
    staged={}
    for rel in CONTRACTS:
        p=folia/JAVA/rel
        staged[p]=transform(rel,p.read_text())
    payload=HELPER_SRC.read_text()
    dest=folia/JAVA/'net/minecraft/world/level/chunk/NeverOverworldEcologyR13.java'
    if dest.exists() and dest.read_text()!=payload:raise ValueError('Conflicting FIELD-R13 helper')
    staged[dest]=payload
    return staged

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folia',type=Path);p.add_argument('--check-only',action='store_true');a=p.parse_args()
    staged=prepare(a.folia.resolve())
    if not a.check_only:
        for path,text in staged.items():path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
    print('[FIELD-R13] fluid reset + height flora + water-support cleanup + post-boundary mine redrain '+('preflight' if a.check_only else 'installed'))

if __name__=='__main__':main()
