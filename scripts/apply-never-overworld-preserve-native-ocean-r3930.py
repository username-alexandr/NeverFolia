#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path

REL=Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")

def fail(m:str): raise SystemExit("[R3930] "+m)

def patch(src:str)->str:
    # Main architectural fix: never erase generated water/lava before rebuilding ocean.
    old='''        removeGeneratedFluids(chunk, minY, FLOOD_LEVEL, air);
        floodSurfaceConnectedVolume(chunk, minY, FLOOD_LEVEL, water);
'''
    if old not in src:
        old='''        removeGeneratedFluids(chunk, minY, FLOOD_LEVEL, air);
        floodSurfaceConnectedAir(chunk, minY, FLOOD_LEVEL, water);
'''
    new='''        // R39.30: native generated ocean is authoritative input, never destructive scratch space.
        // Do NOT erase WATER/LAVA and attempt to reconstruct it afterwards.
        floodSurfaceConnectedVolume(chunk, minY, FLOOD_LEVEL, water);
'''
    if old not in src:
        if "R39.30: native generated ocean is authoritative input" in src:return src
        fail("destructive fluid-reset call sequence not found")
    out=src.replace(old,new,1)

    # Existing transformed helpers use isFloodable() for AIR/replaceable only.
    # Traversal must also cross already-generated water, but writes remain AIR/replaceable only.
    old_guard='''        if (!isFloodable(chunk.getBlockState(pos))) {
            return tail;
        }
'''
    if old_guard in out:
        out=out.replace(old_guard,'''        final BlockState state = chunk.getBlockState(pos);
        if (!isFloodable(state) && !state.is(Blocks.WATER)) {
            return tail;
        }
''')
    # In the BFS pop, preserve WATER and continue traversal; only floodable cells are written.
    old_pop='''            if (!isFloodable(chunk.getBlockState(pos))) {
                continue;
            }

            chunk.setBlockState(pos, water, 0);
'''
    if old_pop in out:
        out=out.replace(old_pop,'''            final BlockState state = chunk.getBlockState(pos);
            if (!isFloodable(state) && !state.is(Blocks.WATER)) {
                continue;
            }
            if (isFloodable(state)) {
                chunk.setBlockState(pos, water, 0);
            }
''')
    # Seed Y=128 from either existing WATER or floodable space.
    old_seed='''                if (!isFloodable(chunk.getBlockState(pos))) {
                    continue;
                }
'''
    if old_seed in out:
        out=out.replace(old_seed,'''                final BlockState state = chunk.getBlockState(pos);
                if (!isFloodable(state) && !state.is(Blocks.WATER)) {
                    continue;
                }
''',1)

    required=("R39.30: native generated ocean is authoritative input","state.is(Blocks.WATER)")
    for x in required:
        if x not in out:fail("missing "+x)
    # Absolute safety gate: the destructive call must be gone from apply().
    apply=out.split("public static void apply",1)[1].split("}",1)[0]
    if "removeGeneratedFluids(" in apply:fail("destructive reset still called")
    return out

def self_test():
    fixture='''class NeverOverworldFlood {
 void apply(){
        removeGeneratedFluids(chunk, minY, FLOOD_LEVEL, air);
        floodSurfaceConnectedVolume(chunk, minY, FLOOD_LEVEL, water);
 }
 void f(){
        if (!isFloodable(chunk.getBlockState(pos))) {
            return tail;
        }
            if (!isFloodable(chunk.getBlockState(pos))) {
                continue;
            }

            chunk.setBlockState(pos, water, 0);
 }
}'''
    out=patch(fixture)
    if "removeGeneratedFluids(chunk" in out:fail("self-test retained destructive call")
    print("R3930_PRESERVE_NATIVE_OCEAN_SELF_TEST_OK")

def main():
    ap=argparse.ArgumentParser();ap.add_argument("folia",nargs="?",type=Path);ap.add_argument("--self-test",action="store_true");a=ap.parse_args()
    if a.self_test:self_test();return
    if a.folia is None:ap.error("folia path required")
    p=a.folia/REL
    if not p.is_file():fail("NeverOverworldFlood.java missing")
    out=patch(p.read_text())
    p.write_text(out)
    print("R3930 native ocean preservation installed",p)

if __name__=="__main__":main()
