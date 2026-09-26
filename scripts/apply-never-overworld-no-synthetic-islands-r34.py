#!/usr/bin/env python3
"""FIELD-R34: disable synthetic dungeon islands and require natural dry terrain.

R30/R24 could lift external StructureStart pieces and manufacture stone/dirt
support under them. In practice the support materializes as chunk-aligned
rectangles. R34 keeps the R19 dry-terrain admission table and spawn frequency,
but rejects surface candidates that do not already fit natural dry terrain.
"""
from __future__ import annotations
import argparse
from pathlib import Path

JAVA=Path("folia-server/src/minecraft/java")
HELPER=JAVA/"net/minecraft/world/level/chunk/NeverOverworldExternalStructurePolicyR19.java"

def fail(msg:str)->None:
    raise ValueError("[FIELD-R34] "+msg)

def method_bounds(text:str, signature:str)->tuple[int,int]:
    start=text.find(signature)
    if start<0: fail("method signature missing: "+signature)
    brace=text.find("{",start)
    if brace<0: fail("method opening brace missing: "+signature)
    depth=0
    i=brace
    in_string=False
    escaped=False
    while i<len(text):
        ch=text[i]
        if in_string:
            if escaped: escaped=False
            elif ch=="\\": escaped=True
            elif ch=='"': in_string=False
            i+=1; continue
        if ch=='"':
            in_string=True; i+=1; continue
        if ch=="{": depth+=1
        elif ch=="}":
            depth-=1
            if depth==0: return start,i+1
        i+=1
    fail("unterminated method: "+signature)

def replace_method(text:str, signature:str, replacement:str)->str:
    a,b=method_bounds(text,signature)
    return text[:a]+replacement+text[b:]

REGISTER="""    private static void registerSyntheticIsland(
        final ChunkPos origin,
        final ResourceKey<Level> dimension,
        final int radius,
        final int topY,
        final StructureStart start
    ) {
        // R34: synthetic support islands are disabled. Surface structures must
        // already fit naturally dry NeverOverworld terrain.
    }"""

APPLY="""    public static int applySyntheticIslands(final ServerLevel level, final ChunkAccess chunk) {
        // R34 compatibility no-op for the historical Moonrise hook.
        return 0;
    }"""

ALLOWS="""    static boolean allows(
        final ChunkGenerator generator,
        final Holder<Structure> structure,
        final RandomState randomState,
        final ChunkAccess heightAccessor,
        final ChunkPos chunkPos,
        final ResourceKey<Level> dimension
    ) {
        if (!inScope(dimension, heightAccessor)) return true;
        final String id = structureId(structure);
        final int radius = radiusForId(id);
        if (radius <= 0) return true;
        if (isBetterMonumentId(id)) {
            return monumentTerrainAllowed(generator, randomState, heightAccessor, chunkPos);
        }
        return dryAt(
            generator,
            randomState,
            heightAccessor,
            chunkPos.getMiddleBlockX(),
            chunkPos.getMiddleBlockZ()
        );
    }"""

ALLOWS_GENERATED="""    static boolean allowsGenerated(
        final ChunkGenerator generator,
        final Holder<Structure> structure,
        final RandomState randomState,
        final ChunkAccess heightAccessor,
        final ChunkPos chunkPos,
        final StructureStart start,
        final ResourceKey<Level> dimension
    ) {
        if (!inScope(dimension, heightAccessor)) return true;
        final String id = structureId(structure);
        final int radius = radiusForId(id);
        if (radius <= 0) return true;
        if (start == null || !start.isValid()) return false;

        // Generated-piece footprint is authoritative. No lifting and no
        // manufactured support: every occupied X/Z column must already have
        // natural WORLD_SURFACE_WG above the flood plane.
        for (final StructurePiece piece : start.getPieces()) {
            final BoundingBox box = piece.getBoundingBox();
            final long width = (long)box.maxX() - box.minX() + 1L;
            final long depth = (long)box.maxZ() - box.minZ() + 1L;
            if (width <= 0L || depth <= 0L || width > MAX_PIECE_SPAN || depth > MAX_PIECE_SPAN) {
                return false;
            }
            for (int z = box.minZ(); z <= box.maxZ(); ++z) {
                for (int x = box.minX(); x <= box.maxX(); ++x) {
                    if (!dryAt(generator, randomState, heightAccessor, x, z)) {
                        return false;
                    }
                }
            }
        }
        return true;
    }"""

def patch(text:str)->str:
    # Idempotency marker.
    if "R34 compatibility no-op for the historical Moonrise hook" in text:
        return text
    text=replace_method(text,"    private static void registerSyntheticIsland(",REGISTER)
    text=replace_method(text,"    public static int applySyntheticIslands(",APPLY)
    text=replace_method(text,"    static boolean allows(",ALLOWS)
    text=replace_method(text,"    static boolean allowsGenerated(",ALLOWS_GENERATED)
    return text

def verify(text:str)->None:
    for marker in (
        "R34 compatibility no-op for the historical Moonrise hook",
        "Surface structures must",
        "every occupied X/Z column must already have",
        "return dryAt(",
    ):
        if marker not in text: fail("missing marker: "+marker)
    for forbidden in (
        "piece.move(0, deltaY, 0)",
        "Blocks.GRASS_BLOCK.defaultBlockState()",
        "chunk.setBlockState(pos, replacement, 0)",
        "registerSyntheticIsland(\n            chunkPos",
    ):
        if forbidden in text: fail("synthetic-island behavior survived: "+forbidden)

def self_test()->None:
    fixture="""class NeverOverworldExternalStructurePolicyR19 {
    private static void registerSyntheticIsland(final ChunkPos origin, final ResourceKey<Level> dimension, final int radius, final int topY, final StructureStart start) { x(); }
    public static int applySyntheticIslands(final ServerLevel level, final ChunkAccess chunk) { return 9; }
    static boolean allows(final ChunkGenerator generator, final Holder<Structure> structure, final RandomState randomState, final ChunkAccess heightAccessor, final ChunkPos chunkPos, final ResourceKey<Level> dimension) { return true; }
    static boolean allowsGenerated(final ChunkGenerator generator, final Holder<Structure> structure, final RandomState randomState, final ChunkAccess heightAccessor, final ChunkPos chunkPos, final StructureStart start, final ResourceKey<Level> dimension) { piece.move(0, deltaY, 0); return true; }
}
"""
    out=patch(fixture)
    verify(out)
    if patch(out)!=out: fail("transform is not idempotent")
    print("[FIELD-R34] SELF-TEST OK")

def main()->None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia",nargs="?",type=Path)
    p.add_argument("--self-test",action="store_true")
    p.add_argument("--check-only",action="store_true")
    a=p.parse_args()
    if a.self_test:
        self_test(); return
    if a.folia is None: p.error("folia worktree is required")
    path=a.folia.resolve()/HELPER
    if not path.is_file(): fail("R19 materialized helper missing")
    text=path.read_text(encoding="utf-8")
    if a.check_only:
        verify(text)
        print("[FIELD-R34] natural-dry external structure invariants OK")
        return
    self_test()
    text=patch(text)
    verify(text)
    path.write_text(text,encoding="utf-8")
    print("[FIELD-R34] installed: synthetic islands disabled")

if __name__=="__main__":
    main()
