#!/usr/bin/env python3
"""R32: reject narrow deep apertures in the final NeverOverworld primary flood.

Install late, after the historical R9->R15 exact-source chain and the R22
fixpack. This intentionally does not alter any historical source contract.
"""
from __future__ import annotations
import argparse
from pathlib import Path

JAVA=Path("folia-server/src/minecraft/java")
FLOOD=JAVA/"net/minecraft/world/level/chunk/NeverOverworldFlood.java"

CONSTANT_ANCHOR="    private static final int FLOOD_LEVEL = 128;\n"
CONSTANTS="""    private static final int DEEP_FLOW_MAX_Y = 96;
    private static final int MIN_DEEP_APERTURE = 6;
"""
WRITE_OLD="""            if (!chunk.getBlockState(pos).isAir()) {
                continue;
            }

            chunk.setBlockState(pos, water, 0);
"""
WRITE_NEW="""            if (!chunk.getBlockState(pos).isAir()) {
                continue;
            }
            if (y <= DEEP_FLOW_MAX_Y
                && !hydraulicOpenAir(chunk, localX, y, localZ, minX, minZ)) {
                continue;
            }

            chunk.setBlockState(pos, water, 0);
"""
HELPER_ANCHOR="    private static int encode(final int localX, final int y, final int localZ, final int minY) {\n"
HELPER="""    private static boolean hydraulicOpenAir(
        final ChunkAccess chunk,
        final int localX,
        final int y,
        final int localZ,
        final int minX,
        final int minZ
    ) {
        if (y > DEEP_FLOW_MAX_Y) {
            return true;
        }
        final BlockPos.MutableBlockPos probe = new BlockPos.MutableBlockPos();
        int open = 0;
        for (int dz = -1; dz <= 1; ++dz) {
            for (int dx = -1; dx <= 1; ++dx) {
                final int x = localX + dx;
                final int z = localZ + dz;
                if (x < 0 || x > 15 || z < 0 || z > 15) {
                    continue;
                }
                probe.set(minX + x, y, minZ + z);
                if (chunk.getBlockState(probe).isAir() && ++open >= MIN_DEEP_APERTURE) {
                    return true;
                }
            }
        }
        return false;
    }

"""

def fail(message:str)->None:
    raise ValueError("[FIELD-R32] "+message)

def patch(text:str)->str:
    installed=(CONSTANTS in text, WRITE_NEW in text, HELPER in text)
    if all(installed):
        return text
    if any(installed):
        fail("partial deep-aperture installation")
    if text.count(CONSTANT_ANCHOR)!=1:
        fail("FLOOD_LEVEL anchor missing/duplicated")
    if text.count(WRITE_OLD)!=1:
        fail(f"primary flood write anchor count={text.count(WRITE_OLD)}")
    if text.count(HELPER_ANCHOR)!=1:
        fail("encode anchor missing/duplicated")
    text=text.replace(CONSTANT_ANCHOR,CONSTANT_ANCHOR+CONSTANTS,1)
    text=text.replace(WRITE_OLD,WRITE_NEW,1)
    text=text.replace(HELPER_ANCHOR,HELPER+HELPER_ANCHOR,1)
    return text

def verify_text(text:str)->None:
    for marker in (
        "DEEP_FLOW_MAX_Y = 96",
        "MIN_DEEP_APERTURE = 6",
        "hydraulicOpenAir(",
        "y <= DEEP_FLOW_MAX_Y",
        "open >= MIN_DEEP_APERTURE",
    ):
        if marker not in text: fail("missing marker: "+marker)
    if WRITE_OLD in text: fail("ungated primary flood write survived")

def self_test()->None:
    fixture="""class NeverOverworldFlood {
    private static final int FLOOD_LEVEL = 128;
    void flood(ChunkAccess chunk, BlockPos.MutableBlockPos pos, BlockState water, int y, int localX, int localZ, int minX, int minZ) {
            if (!chunk.getBlockState(pos).isAir()) {
                continue;
            }

            chunk.setBlockState(pos, water, 0);
    }
    private static int encode(final int localX, final int y, final int localZ, final int minY) {
        return 0;
    }
}
"""
    out=patch(fixture)
    verify_text(out)
    if patch(out)!=out: fail("transformer not idempotent")
    print("[FIELD-R32] SELF-TEST OK")

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia",nargs="?",type=Path)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--check-only",action="store_true")
    a=p.parse_args()
    if a.self_test:
        self_test(); return
    if a.folia is None:
        p.error("folia worktree is required")
    path=a.folia.resolve()/FLOOD
    if not path.is_file(): fail("NeverOverworldFlood missing")
    text=path.read_text(encoding="utf-8")
    if a.check_only:
        verify_text(text)
        print("[FIELD-R32] final deep-aperture invariants OK")
        return
    self_test()
    out=patch(text)
    verify_text(out)
    path.write_text(out,encoding="utf-8")
    print("[FIELD-R32] installed after historical flood contracts")

if __name__=="__main__":
    main()
