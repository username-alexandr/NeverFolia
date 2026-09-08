#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

TASKS_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/status/ChunkStatusTasks.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldOreExposurePruner.java")
CALL_PREFIX = "net.minecraft.world.level.chunk.NeverOverworldOreExposurePruner.apply("

HELPER = r'''package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

public final class NeverOverworldOreExposurePruner {
    private static final int MIN_Y = -496;
    private static final int MAX_Y = -96;
    private static final int EXPOSED_RETAIN_PERCENT = 8;
    private static final long SALT = 0x6E657665724F7265L;

    private NeverOverworldOreExposurePruner() {}

    public static void apply(final ServerLevel level, final ChunkAccess chunk) {
        if (level.dimension() != Level.OVERWORLD || level.getMinY() != -512 || level.getHeight() != 1024) return;

        final ChunkPos chunkPos = chunk.getPos();
        final int minX = chunkPos.getMinBlockX();
        final int maxX = chunkPos.getMaxBlockX();
        final int minZ = chunkPos.getMinBlockZ();
        final int maxZ = chunkPos.getMaxBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();

        // Native deep ores are placed at SURFACE before CARVERS. At CARVERS we
        // finally know the cave faces. Skip whole 16-block sections whose palette
        // cannot contain an ore, then inspect only ore voxels in matching sections.
        // This avoids scanning every cave-air voxel and keeps the field correction
        // cheap even with the 1024-block NeverOverworld dimension.
        final int minSectionY = MIN_Y >> 4;
        final int maxSectionY = MAX_Y >> 4;
        for (int sectionY = minSectionY; sectionY <= maxSectionY; ++sectionY) {
            final LevelChunkSection section = chunk.getSection(chunk.getSectionIndexFromSectionY(sectionY));
            if (!section.maybeHas(state -> hostFor(state.getBlock()) != null)) continue;

            final int sectionBaseY = sectionY << 4;
            final int localMinY = Math.max(0, MIN_Y - sectionBaseY);
            final int localMaxY = Math.min(15, MAX_Y - sectionBaseY);
            for (int localY = localMinY; localY <= localMaxY; ++localY) {
                final int y = sectionBaseY + localY;
                for (int localZ = 0; localZ < 16; ++localZ) {
                    final int z = minZ + localZ;
                    for (int localX = 0; localX < 16; ++localX) {
                        final BlockState state = section.getBlockState(localX, localY, localZ);
                        final Block host = hostFor(state.getBlock());
                        if (host == null) continue;
                        final int x = minX + localX;
                        if (!isExposed(chunk, x, y, z, minX, maxX, minZ, maxZ)) continue;
                        if (retain(level.getSeed(), x, y, z)) continue;
                        chunk.setBlockState(pos.set(x, y, z), host.defaultBlockState(), 0);
                    }
                }
            }
        }
    }

    private static boolean isExposed(
        final ChunkAccess chunk,
        final int x,
        final int y,
        final int z,
        final int minX,
        final int maxX,
        final int minZ,
        final int maxZ
    ) {
        if (chunk.getBlockState(x, y - 1, z).isAir() || chunk.getBlockState(x, y + 1, z).isAir()) return true;
        // Never read mutable neighbour chunks during generation. Chunk-edge ores
        // are checked vertically and toward owned horizontal neighbours only.
        if (x > minX && chunk.getBlockState(x - 1, y, z).isAir()) return true;
        if (x < maxX && chunk.getBlockState(x + 1, y, z).isAir()) return true;
        if (z > minZ && chunk.getBlockState(x, y, z - 1).isAir()) return true;
        return z < maxZ && chunk.getBlockState(x, y, z + 1).isAir();
    }

    private static Block hostFor(final Block block) {
        if (block == Blocks.DEEPSLATE_COAL_ORE || block == Blocks.DEEPSLATE_IRON_ORE || block == Blocks.DEEPSLATE_COPPER_ORE || block == Blocks.DEEPSLATE_GOLD_ORE || block == Blocks.DEEPSLATE_REDSTONE_ORE || block == Blocks.DEEPSLATE_LAPIS_ORE || block == Blocks.DEEPSLATE_DIAMOND_ORE || block == Blocks.DEEPSLATE_EMERALD_ORE) return Blocks.DEEPSLATE;
        if (block == Blocks.COAL_ORE || block == Blocks.IRON_ORE || block == Blocks.COPPER_ORE || block == Blocks.GOLD_ORE || block == Blocks.REDSTONE_ORE || block == Blocks.LAPIS_ORE || block == Blocks.DIAMOND_ORE || block == Blocks.EMERALD_ORE) return Blocks.STONE;
        return null;
    }

    private static boolean retain(final long seed, final int x, final int y, final int z) {
        long value = seed ^ SALT;
        value ^= (long)x * 0x9E3779B97F4A7C15L;
        value ^= (long)y * 0xC2B2AE3D27D4EB4FL;
        value ^= (long)z * 0x165667B19E3779F9L;
        value = mix64(value);
        return Math.floorMod(value, 100L) < EXPOSED_RETAIN_PERCENT;
    }

    private static long mix64(long z) {
        z = (z ^ (z >>> 30)) * 0xBF58476D1CE4E5B9L;
        z = (z ^ (z >>> 27)) * 0x94D049BB133111EBL;
        return z ^ (z >>> 31);
    }
}
'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld ore exposure r6] {message}")


def matching(source: str, start: int, opening: str, closing: str) -> int:
    depth=0; in_string=False; in_char=False; escaped=False; i=start
    while i < len(source):
        ch=source[i]; nxt=source[i+1] if i+1 < len(source) else ""
        if in_string:
            if escaped: escaped=False
            elif ch=="\\": escaped=True
            elif ch=='"': in_string=False
            i+=1; continue
        if in_char:
            if escaped: escaped=False
            elif ch=="\\": escaped=True
            elif ch=="'": in_char=False
            i+=1; continue
        if ch=='"': in_string=True; i+=1; continue
        if ch=="'": in_char=True; i+=1; continue
        if ch=="/" and nxt=="/":
            nl=source.find("\n",i+2); i=len(source) if nl<0 else nl+1; continue
        if ch=="/" and nxt=="*":
            end=source.find("*/",i+2)
            if end<0: fail("unterminated block comment")
            i=end+2; continue
        if ch==opening: depth+=1
        elif ch==closing:
            depth-=1
            if depth==0: return i
        i+=1
    fail(f"unterminated {opening}{closing}")


def method_bounds(source: str) -> tuple[int,int,str,str]:
    method=re.search(r"static\s+CompletableFuture\s*<\s*ChunkAccess\s*>\s+generateCarvers\s*\(",source)
    if method is None: fail("generateCarvers not found")
    po=source.find("(",method.start(),method.end()); pc=matching(source,po,"(",")")
    params=source[po+1:pc]
    cm=re.search(r"\bWorldGenContext\s+(\w+)\b",params); chm=re.search(r"\bChunkAccess\s+(\w+)\b",params)
    if cm is None or chm is None: fail("generateCarvers parameter names unresolved")
    bo=pc+1
    while bo<len(source) and source[bo].isspace(): bo+=1
    if source[bo]!="{": fail("generateCarvers body missing")
    bc=matching(source,bo,"{","}")
    return bo,bc,cm.group(1),chm.group(1)


def inject(source: str) -> str:
    if CALL_PREFIX in source: fail("exposure pruner already injected")
    bo,bc,context,chunk=method_bounds(source)
    body=source[bo+1:bc]
    calls=list(re.finditer(r"\bapplyCarvers\s*\(",body))
    if len(calls)!=1: fail(f"expected one applyCarvers call, got {len(calls)}")
    abs_start=bo+1+calls[0].start(); po=source.find("(",abs_start,bc); pc=matching(source,po,"(",")")
    semi=pc+1
    while semi<bc and source[semi].isspace() and source[semi]!="\n": semi+=1
    if semi>=bc or source[semi]!=";": fail("applyCarvers call lacks semicolon")
    ls=source.rfind("\n",0,abs_start)+1
    indent=re.match(r"[ \t]*",source[ls:abs_start]).group(0)
    addition=("\n"+indent+"// NeverFolia field-r6: keep cave-facing ores rare after CARVERS.\n"+indent+CALL_PREFIX+f"{context}.level(), {chunk});")
    out=source[:semi+1]+addition+source[semi+1:]
    if out.count(CALL_PREFIX)!=1: fail("pruner call count invalid")
    return out


def self_test() -> None:
    fixture='''class ChunkStatusTasks {\n static CompletableFuture<ChunkAccess> generateCarvers(WorldGenContext ctx, ChunkStep step, StaticCache2D<GenerationChunkHolder> chunks, ChunkAccess center) {\n  ctx.generator().applyCarvers(region, ctx.level().getSeed(), random, biome, structures, center);\n  return CompletableFuture.completedFuture(center);\n }\n}\n'''
    out=inject(fixture)
    if "NeverOverworldOreExposurePruner.apply(ctx.level(), center);" not in out: fail("SELF-TEST: call not injected")
    if "EXPOSED_RETAIN_PERCENT = 8" not in HELPER: fail("SELF-TEST: exposed retain chance drifted")
    if "section.maybeHas" not in HELPER: fail("SELF-TEST: ore-free section skip missing")
    if "Chunk-edge ores" not in HELPER: fail("SELF-TEST: neighbour-ownership guard missing")
    print("[NeverFolia][NeverOverworld ore exposure r6] SELF-TEST OK")


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("folia",nargs="?",type=Path)
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.folia is None: parser.error("folia worktree path required")
    self_test(); root=args.folia.resolve(); tasks=root/TASKS_REL; helper=root/HELPER_REL
    if not tasks.is_file(): fail(f"ChunkStatusTasks missing: {tasks}")
    helper.parent.mkdir(parents=True,exist_ok=True); helper.write_text(HELPER,encoding="utf-8")
    tasks.write_text(inject(tasks.read_text(encoding="utf-8")),encoding="utf-8")
    print("[NeverFolia][NeverOverworld ore exposure r6] post-CARVERS exposure pruning applied")
    print("  exposed ore retain chance: 8%")
    print("  ore-free sections: skipped by palette predicate")


if __name__ == "__main__":
    main()
