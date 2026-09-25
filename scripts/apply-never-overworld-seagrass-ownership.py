#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

FEATURE_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/feature/SeagrassFeature.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/feature/NeverOverworldFeatureOwnership.java")
HOOK = "NeverOverworldFeatureOwnership.rejectOutsideOriginChunk"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld seagrass] {message}")


def resolve_local(source: str, type_name: str, expression: str) -> str:
    pattern = re.compile(
        rf"\b{re.escape(type_name)}\s+(?P<name>\w+)\s*=\s*{expression}\s*;"
    )
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        fail(f"expected exactly one {type_name} local for {expression!r}, got {len(matches)}")
    return matches[0].group("name")


def patch_feature(source: str) -> str:
    if HOOK in source:
        fail("SeagrassFeature is already patched")
    if "class SeagrassFeature" not in source:
        fail("SeagrassFeature class marker not found")

    level = resolve_local(source, "WorldGenLevel", r"\w+\.level\(\)")
    origin = resolve_local(source, "BlockPos", r"\w+\.origin\(\)")
    random = resolve_local(source, "RandomSource", r"\w+\.random\(\)")

    offsets = re.compile(
        rf"^(?P<indent>[ \t]*)int\s+(?P<x>\w+)\s*=\s*{re.escape(random)}\.nextInt\(8\)\s*-\s*{re.escape(random)}\.nextInt\(8\);[ \t]*\n"
        rf"(?P=indent)int\s+(?P<z>\w+)\s*=\s*{re.escape(random)}\.nextInt\(8\)\s*-\s*{re.escape(random)}\.nextInt\(8\);[ \t]*\n",
        re.MULTILINE,
    )
    matches = list(offsets.finditer(source))
    if len(matches) != 1:
        fail(f"expected exactly one SeagrassFeature X/Z offset pair, got {len(matches)}")

    match = matches[0]
    indent = match.group("indent")
    x = match.group("x")
    z = match.group("z")
    guard = (
        match.group(0)
        + f"{indent}// NeverFolia NR-DEV-1: SeagrassFeature offsets up to seven blocks from its\n"
        + f"{indent}// placed-feature origin. Reject a candidate before getHeight/getBlockState so\n"
        + f"{indent}// aquatic decoration never reads or writes a neighboring Folia chunk.\n"
        + f"{indent}if ({HOOK}({level}, {origin}, {origin}.getX() + {x}, {origin}.getZ() + {z})) {{\n"
        + f"{indent}    return false;\n"
        + f"{indent}}}\n"
    )
    patched = source[: match.start()] + guard + source[match.end() :]

    guard_pos = patched.index(HOOK)
    height_pos = patched.find(".getHeight(", guard_pos)
    if height_pos < 0 or guard_pos > height_pos:
        fail("ownership guard was not placed before SeagrassFeature.getHeight")
    if patched.count(HOOK) != 1:
        fail("ownership guard must be injected exactly once")
    return patched


def helper_source() -> str:
    return r'''package net.minecraft.world.level.levelgen.feature;

import net.minecraft.core.BlockPos;
import net.minecraft.core.SectionPos;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;

/** Chunk-ownership rules for NR-DEV-1 features with internal X/Z offsets. */
final class NeverOverworldFeatureOwnership {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;

    private NeverOverworldFeatureOwnership() {}

    static boolean rejectOutsideOriginChunk(
        final WorldGenLevel level,
        final BlockPos origin,
        final int targetX,
        final int targetZ
    ) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != EXPECTED_MIN_Y
            || level.getHeight() != EXPECTED_HEIGHT) {
            return false;
        }

        final int ownerChunkX = SectionPos.blockToSectionCoord(origin.getX());
        final int ownerChunkZ = SectionPos.blockToSectionCoord(origin.getZ());
        return SectionPos.blockToSectionCoord(targetX) != ownerChunkX
            || SectionPos.blockToSectionCoord(targetZ) != ownerChunkZ;
    }
}
'''


def self_test() -> None:
    fixture = '''package net.minecraft.world.level.levelgen.feature;
class SeagrassFeature {
    boolean place(FeaturePlaceContext context) {
        boolean placedAny = false;
        RandomSource random = context.random();
        WorldGenLevel level = context.level();
        BlockPos origin = context.origin();
        Object config = context.config();
        int x = random.nextInt(8) - random.nextInt(8);
        int z = random.nextInt(8) - random.nextInt(8);
        int y = level.getHeight(Heightmap.Types.OCEAN_FLOOR, origin.getX() + x, origin.getZ() + z);
        BlockPos grassPos = new BlockPos(origin.getX() + x, y, origin.getZ() + z);
        return placedAny;
    }
}
'''
    patched = patch_feature(fixture)
    if patched.count(HOOK) != 1:
        fail("SELF-TEST: ownership hook missing")
    if patched.index(HOOK) > patched.index("level.getHeight"):
        fail("SELF-TEST: cross-chunk guard must execute before getHeight")
    helper = helper_source()
    for marker in (
        "EXPECTED_MIN_Y = -512",
        "EXPECTED_HEIGHT = 1024",
        "Level.OVERWORLD",
        "SectionPos.blockToSectionCoord(origin.getX())",
        "SectionPos.blockToSectionCoord(targetX)",
    ):
        if marker not in helper:
            fail(f"SELF-TEST: helper missing {marker!r}")
    print("[NeverFolia][NeverOverworld seagrass] CHUNK OWNERSHIP SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Make NR-DEV-1 SeagrassFeature chunk-owned")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required unless --self-test is used")

    self_test()
    folia = args.folia.resolve()
    feature = folia / FEATURE_REL
    helper = folia / HELPER_REL
    if not feature.is_file():
        fail(f"SeagrassFeature source not found: {feature}")

    feature.write_text(patch_feature(feature.read_text(encoding="utf-8")), encoding="utf-8")
    helper.write_text(helper_source(), encoding="utf-8")
    print("[NeverFolia][NeverOverworld seagrass] chunk-ownership hook applied")
    print(f"  feature: {feature}")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
