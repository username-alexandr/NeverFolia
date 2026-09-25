#!/usr/bin/env python3
"""FIELD-R14: restore verified ocean connectivity and lava exclusion.

Install after FIELD-R13. The old R11 boundary rule treated every shallow
chunk-edge component as ocean-connected. R14 replaces that call with a
conservative verified-water continuation, preserves generated lava, and blocks
water placement/traversal on cells touching lava.
"""
from __future__ import annotations
import argparse
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
JAVA=Path('folia-server/src/minecraft/java')
FLOOD=JAVA/'net/minecraft/world/level/chunk/NeverOverworldFlood.java'
HELPER_SRC=ROOT/'native/neveroverworld/field-r14/java/net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR14.java'
HELPER_DST=JAVA/'net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR14.java'

OLD_BOUNDARY='        NeverOverworldFloodBoundaryR11.apply(level, chunk);'
NEW_BOUNDARY='        NeverOverworldFloodConnectivityR14.apply(level, chunk);'
OLD_FLUID='if (!state.is(Blocks.WATER) && !state.is(Blocks.LAVA)) {'
NEW_FLUID='if (!state.is(Blocks.WATER)) {'
OLD_CHECK='!isFloodable(chunk.getBlockState(pos))'
NEW_CHECK='!isFloodableAt(chunk, pos)'
ANCHOR='    private static boolean isFloodable(final BlockState state) {\n'

METHOD=r'''    private static boolean isFloodableAt(final ChunkAccess chunk, final BlockPos pos) {
        if (!isFloodable(chunk.getBlockState(pos))) return false;
        final int minX = chunk.getPos().getMinBlockX();
        final int minZ = chunk.getPos().getMinBlockZ();
        final int x = pos.getX(), y = pos.getY(), z = pos.getZ();
        final BlockPos.MutableBlockPos probe = new BlockPos.MutableBlockPos();
        final int[][] d = {{1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,0,1},{0,0,-1}};
        for (int[] v : d) {
            final int nx=x+v[0], ny=y+v[1], nz=z+v[2];
            if (nx < minX || nx > minX + 15 || nz < minZ || nz > minZ + 15
                || ny < chunk.getMinY() || ny >= chunk.getMaxY()) continue;
            probe.set(nx,ny,nz);
            if (chunk.getBlockState(probe).is(Blocks.LAVA)) return false;
        }
        return true;
    }

'''

def patch(text:str)->str:
    if NEW_BOUNDARY in text and 'private static boolean isFloodableAt' in text:
        return text
    if text.count(OLD_BOUNDARY)!=1: raise ValueError('FIELD-R14 boundary anchor mismatch')
    if text.count(OLD_FLUID)!=1: raise ValueError('FIELD-R14 generated-fluid anchor mismatch')
    checks=text.count(OLD_CHECK)
    if checks < 2: raise ValueError(f'FIELD-R14 expected floodability guards, got {checks}')
    if text.count(ANCHOR)!=1: raise ValueError('FIELD-R14 isFloodable anchor mismatch')
    text=text.replace(OLD_BOUNDARY,NEW_BOUNDARY,1)
    text=text.replace(OLD_FLUID,NEW_FLUID,1)
    text=text.replace(OLD_CHECK,NEW_CHECK)
    text=text.replace(ANCHOR,METHOD+ANCHOR,1)
    return text

def prepare(folia:Path):
    flood=folia/FLOOD
    if not flood.is_file(): raise ValueError('NeverOverworldFlood missing')
    out=patch(flood.read_text())
    helper=HELPER_SRC.read_text()
    dest=folia/HELPER_DST
    if dest.exists() and dest.read_text()!=helper: raise ValueError('Conflicting FIELD-R14 helper')
    return {flood:out,dest:helper}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folia',type=Path)
    p.add_argument('--check-only',action='store_true')
    a=p.parse_args()
    staged=prepare(a.folia.resolve())
    if not a.check_only:
        for path,text in staged.items():
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(text)
    print('[FIELD-R14] verified ocean connectivity + preserve lava + lava-adjacent flood barrier '+('preflight' if a.check_only else 'installed'))

if __name__=='__main__': main()
