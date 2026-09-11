#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

TASKS_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/status/ChunkStatusTasks.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldOreExposurePruner.java")
CARVER_CALL = "net.minecraft.world.level.chunk.NeverOverworldOreExposurePruner.applyAfterCarvers("
FEATURE_CALL = "net.minecraft.world.level.chunk.NeverOverworldOreExposurePruner.applyAfterFeatures("

HELPER = r'''package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;

/**
 * NeverOverworld ore scarcity correction.
 *
 * Deep native ores exist before CARVERS, so cave-facing deep ore is corrected
 * immediately after carving. Vanilla resource ores are placed later during
 * FEATURES, so a second pass runs after biome decoration. The latter both
 * reduces total upper-world ore density and strongly suppresses ore exposed to
 * the enormous flooded caves visible in field screenshots.
 *
 * Both passes read/write only the owning chunk. Horizontal neighbour chunks are
 * deliberately never observed so Folia chunk-order determinism is preserved.
 */
public final class NeverOverworldOreExposurePruner {
    private static final int DEEP_MIN_Y = -496;
    private static final int DEEP_MAX_Y = -96;
    private static final int UPPER_MIN_Y = -64;
    private static final int UPPER_MAX_Y = 319;
    private static final long DEEP_SALT = 0x6E657665724F7265L;
    private static final long UPPER_SALT = 0x5265647563654F72L;

    private NeverOverworldOreExposurePruner() {}

    public static void applyAfterCarvers(final ServerLevel level, final ChunkAccess chunk) {
        if (!isNeverOverworld(level)) return;
        prune(level, chunk, DEEP_MIN_Y, DEEP_MAX_Y, true);
    }

    public static void applyAfterFeatures(final ServerLevel level, final ChunkAccess chunk) {
        if (!isNeverOverworld(level)) return;
        prune(level, chunk, UPPER_MIN_Y, UPPER_MAX_Y, false);
    }

    private static boolean isNeverOverworld(final ServerLevel level) {
        return level.dimension() == Level.OVERWORLD && level.getMinY() == -512 && level.getHeight() == 1024;
    }

    private static void prune(
        final ServerLevel level,
        final ChunkAccess chunk,
        final int minY,
        final int maxY,
        final boolean deepStage
    ) {
        final ChunkPos chunkPos = chunk.getPos();
        final int minX = chunkPos.getMinBlockX();
        final int maxX = chunkPos.getMaxBlockX();
        final int minZ = chunkPos.getMinBlockZ();
        final int maxZ = chunkPos.getMaxBlockZ();
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        final BlockPos.MutableBlockPos probe = new BlockPos.MutableBlockPos();

        final int minSectionY = minY >> 4;
        final int maxSectionY = maxY >> 4;
        for (int sectionY = minSectionY; sectionY <= maxSectionY; ++sectionY) {
            final LevelChunkSection section = chunk.getSection(chunk.getSectionIndexFromSectionY(sectionY));
            if (!section.maybeHas(state -> profileFor(state.getBlock()) != null)) continue;

            final int sectionBaseY = sectionY << 4;
            final int localMinY = Math.max(0, minY - sectionBaseY);
            final int localMaxY = Math.min(15, maxY - sectionBaseY);
            for (int localY = localMinY; localY <= localMaxY; ++localY) {
                final int y = sectionBaseY + localY;
                for (int localZ = 0; localZ < 16; ++localZ) {
                    final int z = minZ + localZ;
                    for (int localX = 0; localX < 16; ++localX) {
                        final BlockState state = section.getBlockState(localX, localY, localZ);
                        final OreProfile profile = profileFor(state.getBlock());
                        if (profile == null) continue;

                        final int x = minX + localX;
                        final boolean exposed = isExposed(chunk, probe, x, y, z, minX, maxX, minZ, maxZ);
                        final int retainPercent;
                        if (deepStage) {
                            if (!exposed) continue; // buried deep density is tuned by field-R7 geometry frequency
                            retainPercent = profile.deepExposedRetain;
                        } else {
                            retainPercent = exposed ? profile.upperExposedRetain : profile.upperBuriedRetain;
                        }

                        final long salt = deepStage ? DEEP_SALT : UPPER_SALT;
                        if (retain(level.getSeed(), x, y, z, profile, retainPercent, salt)) continue;
                        final Block host = hostFor(state.getBlock());
                        if (host != null) {
                            chunk.setBlockState(pos.set(x, y, z), host.defaultBlockState(), 0);
                        }
                    }
                }
            }
        }
    }

    private static boolean isExposed(
        final ChunkAccess chunk,
        final BlockPos.MutableBlockPos probe,
        final int x,
        final int y,
        final int z,
        final int minX,
        final int maxX,
        final int minZ,
        final int maxZ
    ) {
        if (isExposureState(chunk.getBlockState(probe.set(x, y - 1, z)))
            || isExposureState(chunk.getBlockState(probe.set(x, y + 1, z)))) return true;

        // Never read mutable neighbour chunks during generation. Chunk-edge ores
        // are checked vertically and only toward horizontal positions owned by
        // this chunk; this keeps generation independent of neighbouring order.
        if (x > minX && isExposureState(chunk.getBlockState(probe.set(x - 1, y, z)))) return true;
        if (x < maxX && isExposureState(chunk.getBlockState(probe.set(x + 1, y, z)))) return true;
        if (z > minZ && isExposureState(chunk.getBlockState(probe.set(x, y, z - 1)))) return true;
        return z < maxZ && isExposureState(chunk.getBlockState(probe.set(x, y, z + 1)));
    }

    private static boolean isExposureState(final BlockState state) {
        return state.isAir() || !state.getFluidState().isEmpty();
    }

    private static OreProfile profileFor(final Block block) {
        if (block == Blocks.COAL_ORE || block == Blocks.DEEPSLATE_COAL_ORE) return OreProfile.COAL;
        if (block == Blocks.IRON_ORE || block == Blocks.DEEPSLATE_IRON_ORE) return OreProfile.IRON;
        if (block == Blocks.COPPER_ORE || block == Blocks.DEEPSLATE_COPPER_ORE) return OreProfile.COPPER;
        if (block == Blocks.GOLD_ORE || block == Blocks.DEEPSLATE_GOLD_ORE) return OreProfile.GOLD;
        if (block == Blocks.REDSTONE_ORE || block == Blocks.DEEPSLATE_REDSTONE_ORE) return OreProfile.REDSTONE;
        if (block == Blocks.LAPIS_ORE || block == Blocks.DEEPSLATE_LAPIS_ORE) return OreProfile.LAPIS;
        if (block == Blocks.DIAMOND_ORE || block == Blocks.DEEPSLATE_DIAMOND_ORE) return OreProfile.DIAMOND;
        if (block == Blocks.EMERALD_ORE || block == Blocks.DEEPSLATE_EMERALD_ORE) return OreProfile.EMERALD;
        return null;
    }

    private static Block hostFor(final Block block) {
        if (block == Blocks.DEEPSLATE_COAL_ORE || block == Blocks.DEEPSLATE_IRON_ORE || block == Blocks.DEEPSLATE_COPPER_ORE || block == Blocks.DEEPSLATE_GOLD_ORE || block == Blocks.DEEPSLATE_REDSTONE_ORE || block == Blocks.DEEPSLATE_LAPIS_ORE || block == Blocks.DEEPSLATE_DIAMOND_ORE || block == Blocks.DEEPSLATE_EMERALD_ORE) return Blocks.DEEPSLATE;
        if (block == Blocks.COAL_ORE || block == Blocks.IRON_ORE || block == Blocks.COPPER_ORE || block == Blocks.GOLD_ORE || block == Blocks.REDSTONE_ORE || block == Blocks.LAPIS_ORE || block == Blocks.DIAMOND_ORE || block == Blocks.EMERALD_ORE) return Blocks.STONE;
        return null;
    }

    private static boolean retain(
        final long seed,
        final int x,
        final int y,
        final int z,
        final OreProfile profile,
        final int retainPercent,
        final long stageSalt
    ) {
        if (retainPercent >= 100) return true;
        if (retainPercent <= 0) return false;
        long value = seed ^ stageSalt ^ profile.salt;
        value ^= (long)x * 0x9E3779B97F4A7C15L;
        value ^= (long)y * 0xC2B2AE3D27D4EB4FL;
        value ^= (long)z * 0x165667B19E3779F9L;
        value = mix64(value);
        return Math.floorMod(value, 100L) < retainPercent;
    }

    private static long mix64(long z) {
        z = (z ^ (z >>> 30)) * 0xBF58476D1CE4E5B9L;
        z = (z ^ (z >>> 27)) * 0x94D049BB133111EBL;
        return z ^ (z >>> 31);
    }

    private enum OreProfile {
        // deep-exposed, upper-buried, upper-exposed
        COAL(0x11A2B3C4D5E6F701L, 6, 85, 18),
        IRON(0x22B3C4D5E6F70112L, 6, 90, 20),
        COPPER(0x33C4D5E6F7011223L, 5, 75, 12),
        GOLD(0x44D5E6F701122334L, 4, 75, 8),
        REDSTONE(0x55E6F70112233445L, 4, 85, 8),
        LAPIS(0x66F7011223344556L, 3, 80, 6),
        DIAMOND(0x77A8122334455667L, 2, 70, 3),
        EMERALD(0x18B9233445566778L, 3, 80, 5);

        final long salt;
        final int deepExposedRetain;
        final int upperBuriedRetain;
        final int upperExposedRetain;

        OreProfile(
            final long salt,
            final int deepExposedRetain,
            final int upperBuriedRetain,
            final int upperExposedRetain
        ) {
            this.salt = salt;
            this.deepExposedRetain = deepExposedRetain;
            this.upperBuriedRetain = upperBuriedRetain;
            this.upperExposedRetain = upperExposedRetain;
        }
    }
}
'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld ore scarcity r7] {message}")


def matching(source: str, start: int, opening: str, closing: str) -> int:
    depth = 0
    in_string = False
    in_char = False
    escaped = False
    i = start
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if in_char:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == "'":
                in_char = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == "'":
            in_char = True
            i += 1
            continue
        if ch == "/" and nxt == "/":
            nl = source.find("\n", i + 2)
            i = len(source) if nl < 0 else nl + 1
            continue
        if ch == "/" and nxt == "*":
            end = source.find("*/", i + 2)
            if end < 0:
                fail("unterminated block comment")
            i = end + 2
            continue
        if ch == opening:
            depth += 1
        elif ch == closing:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    fail(f"unterminated {opening}{closing}")


def method_bounds(source: str, method_name: str) -> tuple[int, int, str, str]:
    method = re.search(
        rf"static\s+CompletableFuture\s*<\s*ChunkAccess\s*>\s+{re.escape(method_name)}\s*\(",
        source,
    )
    if method is None:
        fail(f"{method_name} not found")
    po = source.find("(", method.start(), method.end())
    pc = matching(source, po, "(", ")")
    params = source[po + 1 : pc]
    cm = re.search(r"\bWorldGenContext\s+(\w+)\b", params)
    chm = re.search(r"\bChunkAccess\s+(\w+)\b", params)
    if cm is None or chm is None:
        fail(f"{method_name} parameter names unresolved")
    bo = pc + 1
    while bo < len(source) and source[bo].isspace():
        bo += 1
    if bo >= len(source) or source[bo] != "{":
        fail(f"{method_name} body missing")
    bc = matching(source, bo, "{", "}")
    return bo, bc, cm.group(1), chm.group(1)


def inject_after_call(source: str, method_name: str, called_name: str, call_prefix: str, comment: str) -> str:
    if call_prefix in source:
        fail(f"{method_name} scarcity hook already injected")
    bo, bc, context, chunk = method_bounds(source, method_name)
    body = source[bo + 1 : bc]
    calls = list(re.finditer(rf"\b{re.escape(called_name)}\s*\(", body))
    if len(calls) != 1:
        fail(f"expected one {called_name} call in {method_name}, got {len(calls)}")
    abs_start = bo + 1 + calls[0].start()
    po = source.find("(", abs_start, bc)
    pc = matching(source, po, "(", ")")
    semi = pc + 1
    while semi < bc and source[semi].isspace() and source[semi] != "\n":
        semi += 1
    if semi >= bc or source[semi] != ";":
        fail(f"{called_name} call lacks semicolon")
    ls = source.rfind("\n", 0, abs_start) + 1
    indent = re.match(r"[ \t]*", source[ls:abs_start]).group(0)
    addition = (
        "\n"
        + indent
        + f"// NeverFolia field-R7: {comment}\n"
        + indent
        + call_prefix
        + f"{context}.level(), {chunk});"
    )
    out = source[: semi + 1] + addition + source[semi + 1 :]
    if out.count(call_prefix) != 1:
        fail(f"{method_name} scarcity hook count invalid")
    return out


def inject(source: str) -> str:
    out = inject_after_call(
        source,
        "generateCarvers",
        "applyCarvers",
        CARVER_CALL,
        "prune cave/water-facing native deep ores after CARVERS.",
    )
    out = inject_after_call(
        out,
        "generateFeatures",
        "applyBiomeDecoration",
        FEATURE_CALL,
        "reduce upper vanilla ores after FEATURES, with stronger air/water exposure pruning.",
    )
    return out


def self_test() -> None:
    fixture = '''class ChunkStatusTasks {
 static CompletableFuture<ChunkAccess> generateCarvers(WorldGenContext ctx, ChunkStep step, StaticCache2D<GenerationChunkHolder> chunks, ChunkAccess center) {
  ctx.generator().applyCarvers(region, ctx.level().getSeed(), random, biome, structures, center);
  return CompletableFuture.completedFuture(center);
 }
 static CompletableFuture<ChunkAccess> generateFeatures(WorldGenContext ctx, ChunkStep step, StaticCache2D<GenerationChunkHolder> chunks, ChunkAccess center) {
  ctx.generator().applyBiomeDecoration(region, center, structures);
  return CompletableFuture.completedFuture(center);
 }
}
'''
    out = inject(fixture)
    if "applyAfterCarvers(ctx.level(), center);" not in out:
        fail("SELF-TEST: post-CARVERS call not injected")
    if "applyAfterFeatures(ctx.level(), center);" not in out:
        fail("SELF-TEST: post-FEATURES call not injected")
    required = (
        "UPPER_MIN_Y = -64",
        "UPPER_MAX_Y = 319",
        "state.isAir() || !state.getFluidState().isEmpty()",
        "DIAMOND(0x77A8122334455667L, 2, 70, 3)",
        "COPPER(0x33C4D5E6F7011223L, 5, 75, 12)",
        "COAL(0x11A2B3C4D5E6F701L, 6, 85, 18)",
        "section.maybeHas",
        "Chunk-edge ores",
    )
    for marker in required:
        if marker not in HELPER:
            fail(f"SELF-TEST: helper marker missing: {marker}")
    if "getBlockState(x," in HELPER:
        fail("SELF-TEST: unsupported coordinate getBlockState overload used")
    print("[NeverFolia][NeverOverworld ore scarcity r7] SELF-TEST OK")
    print("  deep exposed retain: coal/iron=6 copper=5 gold/redstone=4 lapis/emerald=3 diamond=2%")
    print("  upper buried retain: coal=85 iron=90 copper/gold=75 redstone=85 lapis/emerald=80 diamond=70%")
    print("  upper exposed retain: coal=18 iron=20 copper=12 gold/redstone=8 lapis=6 diamond=3 emerald=5%")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path required")
    self_test()
    root = args.folia.resolve()
    tasks = root / TASKS_REL
    helper = root / HELPER_REL
    if not tasks.is_file():
        fail(f"ChunkStatusTasks missing: {tasks}")
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text(HELPER, encoding="utf-8")
    tasks.write_text(inject(tasks.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][NeverOverworld ore scarcity r7] two-stage ore pruning installed")
    print("  post-CARVERS: native deep exposed air/fluid pruning")
    print("  post-FEATURES: upper vanilla total-density + air/fluid exposure pruning")


if __name__ == "__main__":
    main()
