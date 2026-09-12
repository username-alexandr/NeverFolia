#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

STRUCTURE_START_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/StructureStart.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/NeverOverworldVillageReclamation.java")
AFTER_PLACE = "            this.structure.afterPlace(level, structureManager, generator, random, chunkBB, chunkPos, this.pieceContainer);\n"
CALL = "            NeverOverworldVillageReclamation.apply(level, this, chunkPos);\n"
MARKER = "NeverFolia R9 V17 actual-bbox village reclamation"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 village reclamation V17] {message}")


def helper_source() -> str:
    return r'''package net.minecraft.world.level.levelgen.structure;

import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.Registries;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.ChunkAccess;

/**
 * NeverFolia R9 V17 actual-bbox village reclamation.
 *
 * <p>The fast-locate path deliberately does not preview Jigsaw placement. Once
 * the real StructureStart is being placed during FEATURES, however, its exact
 * bounding box is authoritative. Reclaim only the intersection with the owning
 * chunk and only below/at the Y=128 flood plane. No neighbouring chunk is read
 * or written and no heightmap/getBaseHeight query is needed.</p>
 *
 * <p>The foundation is installed after vanilla structure placement for the
 * current chunk. Existing non-replaceable structure blocks are preserved. Empty,
 * fluid or replaceable gaps are backfilled downward from Y=128 until natural or
 * structure-solid support is reached (bounded to Y=80). This leaves a solid
 * waterline cap across the real village bbox, so the later LIGHT flood cannot
 * enter the village through Y=128 even when Jigsaw overhangs a shoreline.</p>
 */
public final class NeverOverworldVillageReclamation {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final int FLOOD_LEVEL = 128;
    private static final int FOUNDATION_MIN_Y = 80;
    private static final boolean DEBUG = Boolean.getBoolean("neverfolia.debugVillageReclamation");

    private NeverOverworldVillageReclamation() {}

    public static void apply(final WorldGenLevel level, final StructureStart start, final ChunkPos chunkPos) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != EXPECTED_MIN_Y
            || level.getHeight() != EXPECTED_HEIGHT
            || start == null
            || !start.isValid()) {
            return;
        }

        final String structureId = String.valueOf(
            level.registryAccess().lookupOrThrow(Registries.STRUCTURE).getKey(start.getStructure())
        );
        if (!isVillage(structureId)) {
            return;
        }

        final BoundingBox box = start.getBoundingBox();
        final int chunkMinX = chunkPos.getMinBlockX();
        final int chunkMinZ = chunkPos.getMinBlockZ();
        final int minX = Math.max(box.minX(), chunkMinX);
        final int maxX = Math.min(box.maxX(), chunkMinX + 15);
        final int minZ = Math.max(box.minZ(), chunkMinZ);
        final int maxZ = Math.min(box.maxZ(), chunkMinZ + 15);
        if (minX > maxX || minZ > maxZ) {
            return;
        }

        final ChunkAccess chunk = level.getChunk(chunkPos.x(), chunkPos.z());
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        final boolean desert = "minecraft:village_desert".equals(structureId);
        final BlockState cap = desert ? Blocks.SAND.defaultBlockState() : Blocks.GRASS_BLOCK.defaultBlockState();
        final BlockState shallowFill = desert ? Blocks.SANDSTONE.defaultBlockState() : Blocks.DIRT.defaultBlockState();
        final BlockState deepFill = Blocks.STONE.defaultBlockState();

        int changedColumns = 0;
        int changedBlocks = 0;
        for (int z = minZ; z <= maxZ; ++z) {
            for (int x = minX; x <= maxX; ++x) {
                pos.set(x, FLOOD_LEVEL, z);
                if (!fillable(chunk.getBlockState(pos))) {
                    continue;
                }

                int baseY = FLOOD_LEVEL - 1;
                for (; baseY >= FOUNDATION_MIN_Y; --baseY) {
                    pos.set(x, baseY, z);
                    if (!fillable(chunk.getBlockState(pos))) {
                        break;
                    }
                }

                final int fillStart = Math.max(baseY + 1, FOUNDATION_MIN_Y);
                boolean changed = false;
                for (int y = fillStart; y <= FLOOD_LEVEL; ++y) {
                    pos.set(x, y, z);
                    final BlockState existing = chunk.getBlockState(pos);
                    if (!fillable(existing)) {
                        continue;
                    }
                    final BlockState fill = y == FLOOD_LEVEL
                        ? cap
                        : (y >= FLOOD_LEVEL - 3 ? shallowFill : deepFill);
                    chunk.setBlockState(pos, fill, 0);
                    ++changedBlocks;
                    changed = true;
                }
                if (changed) {
                    ++changedColumns;
                }
            }
        }

        if (DEBUG && changedColumns > 0) {
            System.out.println(
                "[NeverFolia][R9V17_RECLAIM] structure=" + structureId
                    + " chunk=" + chunkPos.x() + "," + chunkPos.z()
                    + " bbox=" + box.minX() + "," + box.minZ() + ".." + box.maxX() + "," + box.maxZ()
                    + " columns=" + changedColumns + " blocks=" + changedBlocks
            );
        }
    }

    private static boolean fillable(final BlockState state) {
        return state.isAir()
            || state.is(Blocks.WATER)
            || state.is(Blocks.LAVA)
            || state.canBeReplaced();
    }

    private static boolean isVillage(final String id) {
        return "minecraft:village_plains".equals(id)
            || "minecraft:village_desert".equals(id)
            || "minecraft:village_savanna".equals(id)
            || "minecraft:village_snowy".equals(id)
            || "minecraft:village_taiga".equals(id);
    }
}
'''


def patch_structure_start(source: str) -> str:
    if CALL in source:
        return source
    count = source.count(AFTER_PLACE)
    if count != 1:
        fail(f"expected exactly one StructureStart.afterPlace anchor, got {count}")
    if "public void placeInChunk(" not in source:
        fail("StructureStart.placeInChunk method missing")
    return source.replace(AFTER_PLACE, AFTER_PLACE + CALL, 1)


def validate(structure_start: str, helper: str) -> None:
    if structure_start.count(CALL) != 1:
        fail("StructureStart must contain exactly one V17 reclamation call")
    for required in (
        MARKER,
        "FLOOD_LEVEL = 128",
        "FOUNDATION_MIN_Y = 80",
        "level.getChunk(chunkPos.x(), chunkPos.z())",
        "Math.max(box.minX(), chunkMinX)",
        "Math.min(box.maxX(), chunkMinX + 15)",
        "chunk.setBlockState(pos, fill, 0)",
        '"minecraft:village_plains"',
        '"minecraft:village_desert"',
        '"minecraft:village_savanna"',
        '"minecraft:village_snowy"',
        '"minecraft:village_taiga"',
    ):
        if required not in helper:
            fail(f"helper missing contract marker: {required}")
    for forbidden in (
        "getBaseHeight(",
        "Structure.generate(",
        "ChunkPos.rangeClosed",
        "moonrise$syncLoadNonFull",
    ):
        if forbidden in helper:
            fail(f"helper contains forbidden cross-chunk/heavy primitive: {forbidden}")


def self_test() -> None:
    fixture = '''package net.minecraft.world.level.levelgen.structure;\nclass StructureStart {\n    public void placeInChunk() {\n        if (true) {\n            this.structure.afterPlace(level, structureManager, generator, random, chunkBB, chunkPos, this.pieceContainer);\n        }\n    }\n}\n'''
    patched = patch_structure_start(fixture)
    helper = helper_source()
    validate(patched, helper)
    if patch_structure_start(patched) != patched:
        fail("SELF-TEST: StructureStart transformer is not idempotent")
    if helper.count("chunk.getBlockState(pos)") < 2:
        fail("SELF-TEST: helper must inspect current chunk state before filling")
    if "if (!fillable(chunk.getBlockState(pos)))" not in helper:
        fail("SELF-TEST: waterline cap must preserve existing structure solids")
    print("[NeverFolia][R9 village reclamation V17] SELF-TEST OK")
    print("  actual Jigsaw bbox is used only at FEATURES placement time")
    print("  writes are clipped to the owning 16x16 chunk")
    print("  waterline foundation: Y=80..128, preserving non-replaceable structure blocks")
    print("  no getBaseHeight / no Structure.generate preview / no neighbour chunk writes")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install V17 actual-bbox village waterline reclamation")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree is required unless --self-test is used")

    self_test()
    root = args.folia.resolve()
    structure_start_path = root / STRUCTURE_START_REL
    helper_path = root / HELPER_REL
    if not structure_start_path.is_file():
        fail(f"StructureStart source missing: {structure_start_path}")

    patched = patch_structure_start(structure_start_path.read_text(encoding="utf-8"))
    helper = helper_source()
    validate(patched, helper)
    structure_start_path.write_text(patched, encoding="utf-8")

    if helper_path.exists():
        existing = helper_path.read_text(encoding="utf-8")
        if MARKER not in existing:
            fail(f"helper path already exists without V17 marker: {helper_path}")
        if existing != helper:
            fail("existing V17 helper differs from expected source")
    else:
        helper_path.write_text(helper, encoding="utf-8")

    print("[NeverFolia][R9 village reclamation V17] actual-bbox reclamation installed")
    print(f"  StructureStart: {structure_start_path}")
    print(f"  helper: {helper_path}")


if __name__ == "__main__":
    main()
