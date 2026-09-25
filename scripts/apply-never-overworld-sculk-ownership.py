#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import tempfile
from pathlib import Path

PATCH_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/feature/SculkPatchFeature.java")
SPREADER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/block/SculkSpreader.java")
BLOCK_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/block/SculkBlock.java")
VEIN_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/block/SculkVeinBlock.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/block/NeverOverworldSculkOwnership.java")

HELPER_FQCN = "net.minecraft.world.level.block.NeverOverworldSculkOwnership"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld sculk] {message}")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        fail(f"{label}: expected exactly one marker, got {count}: {old!r}")
    return source.replace(old, new, 1)


def patch_sculk_patch_feature(source: str) -> str:
    marker = f"{HELPER_FQCN}.rejectFeatureOrigin"
    if marker in source:
        fail("SculkPatchFeature is already patched")
    if "class SculkPatchFeature" not in source:
        fail("SculkPatchFeature class marker not found")

    origin_re = re.compile(
        r"(?P<indent>^[ \t]*)BlockPos\s+(?P<origin>\w+)\s*=\s*(?P<context>\w+)\.origin\(\);[ \t]*$",
        re.MULTILINE,
    )
    matches = list(origin_re.finditer(source))
    if len(matches) != 1:
        fail(f"SculkPatchFeature: expected one origin local, got {len(matches)}")
    match = matches[0]
    indent = match.group("indent")
    origin = match.group("origin")

    prefix = source[: match.start()]
    level_matches = list(re.finditer(r"\bWorldGenLevel\s+(?P<level>\w+)\s*=\s*\w+\.level\(\);", prefix))
    if len(level_matches) != 1:
        fail(f"SculkPatchFeature: expected one WorldGenLevel local, got {len(level_matches)}")
    level = level_matches[0].group("level")

    origin_guard = (
        match.group(0)
        + "\n"
        + f"{indent}// NeverFolia NR-DEV-1: canSpreadFrom reads all six neighbours. Do not let\n"
        + f"{indent}// an origin on the owner-chunk border inspect another Folia generation region.\n"
        + f"{indent}if ({HELPER_FQCN}.rejectFeatureOrigin({level}, {origin})) {{\n"
        + f"{indent}    return false;\n"
        + f"{indent}}}"
    )
    source = source[: match.start()] + origin_guard + source[match.end() :]

    candidate_re = re.compile(
        rf"(?P<indent>^[ \t]*)BlockPos\s+(?P<candidate>\w+)\s*=\s*{re.escape(origin)}\.offset\(.*?\);[ \t]*$",
        re.MULTILINE,
    )
    candidates = list(candidate_re.finditer(source))
    if len(candidates) != 1:
        fail(f"SculkPatchFeature: expected one rare-growth candidate local, got {len(candidates)}")
    candidate_match = candidates[0]
    candidate = candidate_match.group("candidate")
    cindent = candidate_match.group("indent")
    candidate_guard = (
        candidate_match.group(0)
        + "\n"
        + f"{cindent}// NeverFolia NR-DEV-1: extra rare growths use +/-2 X/Z offsets.\n"
        + f"{cindent}if (!{HELPER_FQCN}.allowsFeatureTarget({level}, {origin}, {candidate})) {{\n"
        + f"{cindent}    continue;\n"
        + f"{cindent}}}"
    )
    source = source[: candidate_match.start()] + candidate_guard + source[candidate_match.end() :]

    if source.count(marker) != 1:
        fail("SculkPatchFeature origin guard must be injected exactly once")
    if source.count(f"{HELPER_FQCN}.allowsFeatureTarget") != 1:
        fail("SculkPatchFeature candidate guard must be injected exactly once")
    return source


def patch_sculk_spreader(source: str) -> str:
    if "class SculkSpreader" not in source:
        fail("SculkSpreader class marker not found")
    if "NeverOverworldSculkOwnership.canSpreadVein" in source:
        fail("SculkSpreader is already patched")

    old_spread = "if (spreadVeins && sculkBehaviour.attemptSpreadVein("
    new_spread = (
        "if (spreadVeins "
        "&& NeverOverworldSculkOwnership.canSpreadVein(level, originPos, this.pos, spreader) "
        "&& sculkBehaviour.attemptSpreadVein("
    )
    source = replace_once(source, old_spread, new_spread, "SculkSpreader vein spread")

    movement_re = re.compile(
        r"(?P<indent>^[ \t]*)BlockPos\s+transferPos\s*=\s*getValidMovementPos\(level,\s*this\.pos,\s*random\);[ \t]*$",
        re.MULTILINE,
    )
    matches = list(movement_re.finditer(source))
    if len(matches) != 1:
        fail(f"SculkSpreader movement: expected one transferPos marker, got {len(matches)}")
    match = matches[0]
    indent = match.group("indent")
    replacement = (
        f"{indent}// NeverFolia NR-DEV-1: getValidMovementPos inspects the candidate and its\n"
        f"{indent}// substrate neighbours. Require a two-block owner-chunk margin before reading.\n"
        f"{indent}BlockPos transferPos = NeverOverworldSculkOwnership.canSearchMovement(level, originPos, this.pos, spreader)\n"
        f"{indent}    ? getValidMovementPos(level, this.pos, random)\n"
        f"{indent}    : null;\n"
        f"{indent}if (NeverOverworldSculkOwnership.rejectTransfer(level, originPos, transferPos, spreader)) {{\n"
        f"{indent}    transferPos = null;\n"
        f"{indent}}}"
    )
    source = source[: match.start()] + replacement + source[match.end() :]

    for required in (
        "NeverOverworldSculkOwnership.canSpreadVein",
        "NeverOverworldSculkOwnership.canSearchMovement",
        "NeverOverworldSculkOwnership.rejectTransfer",
    ):
        if source.count(required) != 1:
            fail(f"SculkSpreader: expected exactly one {required}")
    return source


def patch_sculk_block(source: str) -> str:
    if "class SculkBlock" not in source:
        fail("SculkBlock class marker not found")
    if "NeverOverworldSculkOwnership.canCheckGrowth" in source:
        fail("SculkBlock is already patched")

    patterns = (
        "if (!isCloseToCatalyst && canPlaceGrowth(level, chargePos)) {",
        "if (!isCloseToCatalyst && SculkBlock.canPlaceGrowth(level, chargePos)) {",
    )
    found = [p for p in patterns if p in source]
    if len(found) != 1:
        fail(f"SculkBlock: expected one canPlaceGrowth condition marker, got {len(found)}")
    old = found[0]
    new = old.replace(
        "canPlaceGrowth(level, chargePos)",
        "NeverOverworldSculkOwnership.canCheckGrowth(level, originPos, chargePos, spreader) && canPlaceGrowth(level, chargePos)",
    ).replace(
        "SculkBlock.NeverOverworldSculkOwnership", "NeverOverworldSculkOwnership"
    )
    source = replace_once(source, old, new, "SculkBlock growth read window")
    if source.count("NeverOverworldSculkOwnership.canCheckGrowth") != 1:
        fail("SculkBlock growth guard must be injected exactly once")
    return source


def patch_sculk_vein(source: str) -> str:
    if "class SculkVeinBlock" not in source:
        fail("SculkVeinBlock class marker not found")
    if "NeverOverworldSculkOwnership.allowsSculkConversion" in source:
        fail("SculkVeinBlock is already patched")

    support_re = re.compile(
        r"(?P<indent>^[ \t]*)BlockPos\s+(?P<target>\w+)\s*=\s*pos\.relative\((?P<direction>\w+)\);[ \t]*$",
        re.MULTILINE,
    )
    matches = list(support_re.finditer(source))
    usable = []
    for match in matches:
        tail = source[match.end() : match.end() + 240]
        if re.search(rf"getBlockState\(\s*{re.escape(match.group('target'))}\s*\)", tail):
            usable.append(match)
    named = [m for m in usable if m.group("target") == "supportPos"]
    if len(named) == 1:
        match = named[0]
    elif len(usable) == 1:
        match = usable[0]
    else:
        fail(f"SculkVeinBlock: expected one support target marker, got {len(usable)}")

    indent = match.group("indent")
    target = match.group("target")
    guard = (
        match.group(0)
        + "\n"
        + f"{indent}// NeverFolia NR-DEV-1: conversion is followed by MultifaceSpreader.spreadAll.\n"
        + f"{indent}// Keep the support one block inside the owner boundary so all vein writes stay owned.\n"
        + f"{indent}if (!NeverOverworldSculkOwnership.allowsSculkConversion(level, originPos, {target}, spreader)) {{\n"
        + f"{indent}    continue;\n"
        + f"{indent}}}"
    )
    source = source[: match.start()] + guard + source[match.end() :]
    if source.count("NeverOverworldSculkOwnership.allowsSculkConversion") != 1:
        fail("SculkVeinBlock conversion guard must be injected exactly once")
    return source


def helper_source() -> str:
    return r'''package net.minecraft.world.level.block;

import net.minecraft.core.BlockPos;
import net.minecraft.core.SectionPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.LevelAccessor;

/**
 * Folia-safe chunk ownership for vanilla sculk worldgen inside NR-DEV-1.
 * Runtime catalyst spread is intentionally untouched.
 */
public final class NeverOverworldSculkOwnership {
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;

    private NeverOverworldSculkOwnership() {}

    public static boolean rejectFeatureOrigin(final LevelAccessor level, final BlockPos origin) {
        if (!isNeverOverworld(level)) return false;
        return !hasHorizontalMargin(origin, 1);
    }

    public static boolean allowsFeatureTarget(final LevelAccessor level, final BlockPos origin, final BlockPos target) {
        return !isNeverOverworld(level) || sameChunk(origin, target);
    }

    public static boolean canSpreadVein(final LevelAccessor level, final BlockPos origin, final BlockPos cursorPos, final SculkSpreader spreader) {
        if (!active(level, spreader)) return true;
        return sameChunk(origin, cursorPos) && hasHorizontalMargin(cursorPos, 1);
    }

    public static boolean canSearchMovement(final LevelAccessor level, final BlockPos origin, final BlockPos cursorPos, final SculkSpreader spreader) {
        if (!active(level, spreader)) return true;
        return sameChunk(origin, cursorPos) && hasHorizontalMargin(cursorPos, 2);
    }

    public static boolean rejectTransfer(final LevelAccessor level, final BlockPos origin, final BlockPos target, final SculkSpreader spreader) {
        return target != null && active(level, spreader) && !sameChunk(origin, target);
    }

    public static boolean allowsSculkConversion(final LevelAccessor level, final BlockPos origin, final BlockPos target, final SculkSpreader spreader) {
        if (!active(level, spreader)) return true;
        return sameChunk(origin, target) && hasHorizontalMargin(target, 1);
    }

    public static boolean canCheckGrowth(final LevelAccessor level, final BlockPos origin, final BlockPos chargePos, final SculkSpreader spreader) {
        if (!active(level, spreader)) return true;
        return sameChunk(origin, chargePos) && hasHorizontalMargin(chargePos, 4);
    }

    private static boolean active(final LevelAccessor level, final SculkSpreader spreader) {
        return spreader.isWorldGeneration() && isNeverOverworld(level);
    }

    private static boolean isNeverOverworld(final LevelAccessor level) {
        final ServerLevel world = level.getMinecraftWorld();
        return world != null
            && world.dimension().equals(Level.OVERWORLD)
            && level.getMinY() == EXPECTED_MIN_Y
            && level.getHeight() == EXPECTED_HEIGHT;
    }

    private static boolean sameChunk(final BlockPos origin, final BlockPos target) {
        return SectionPos.blockToSectionCoord(origin.getX()) == SectionPos.blockToSectionCoord(target.getX())
            && SectionPos.blockToSectionCoord(origin.getZ()) == SectionPos.blockToSectionCoord(target.getZ());
    }

    private static boolean hasHorizontalMargin(final BlockPos pos, final int margin) {
        final int localX = pos.getX() & 15;
        final int localZ = pos.getZ() & 15;
        return localX >= margin && localX <= 15 - margin
            && localZ >= margin && localZ <= 15 - margin;
    }
}
'''


def self_test() -> None:
    patch_fixture = '''package net.minecraft.world.level.levelgen.feature;
class SculkPatchFeature {
    boolean place(FeaturePlaceContext context) {
        WorldGenLevel level = context.level();
        BlockPos origin = context.origin();
        if (!this.canSpreadFrom(level, origin)) return false;
        for (int i = 0; i < 3; ++i) {
            BlockPos candidate = origin.offset(random.nextInt(5) - 2, 0, random.nextInt(5) - 2);
            if (level.getBlockState(candidate).isAir()) {}
        }
        return true;
    }
}
'''
    spreader_fixture = '''class SculkSpreader {
    class ChargeCursor {
        void update(LevelAccessor level, BlockPos originPos, RandomSource random, SculkSpreader spreader, boolean spreadVeins) {
            if (spreadVeins && sculkBehaviour.attemptSpreadVein(level, this.pos, currentState, this.facings, spreader.isWorldGeneration())) {}
            BlockPos transferPos = getValidMovementPos(level, this.pos, random);
            if (transferPos != null) this.pos = transferPos;
        }
    }
}
'''
    block_fixture = '''class SculkBlock {
    int attemptUseCharge() {
        if (!isCloseToCatalyst && canPlaceGrowth(level, chargePos)) { return 1; }
        return 0;
    }
}
'''
    vein_fixture = '''class SculkVeinBlock {
    boolean attemptPlaceSculk() {
        for (Direction support : DIRECTIONS) {
            BlockPos supportPos = pos.relative(support);
            BlockState supportState = level.getBlockState(supportPos);
        }
        return false;
    }
}
'''

    patched_patch = patch_sculk_patch_feature(patch_fixture)
    patched_spreader = patch_sculk_spreader(spreader_fixture)
    patched_block = patch_sculk_block(block_fixture)
    patched_vein = patch_sculk_vein(vein_fixture)
    helper = helper_source()

    markers = (
        (patched_patch, "rejectFeatureOrigin"),
        (patched_patch, "allowsFeatureTarget"),
        (patched_spreader, "canSpreadVein"),
        (patched_spreader, "canSearchMovement"),
        (patched_spreader, "rejectTransfer"),
        (patched_block, "canCheckGrowth"),
        (patched_vein, "allowsSculkConversion"),
        (helper, "EXPECTED_MIN_Y = -512"),
        (helper, "EXPECTED_HEIGHT = 1024"),
        (helper, "spreader.isWorldGeneration()"),
        (helper, "hasHorizontalMargin(chargePos, 4)"),
    )
    for corpus, marker in markers:
        if marker not in corpus:
            fail(f"SELF-TEST: missing marker {marker!r}")
    if "getValidMovementPos(level, this.pos, random)" not in patched_spreader:
        fail("SELF-TEST: movement call was lost")
    if patched_spreader.index("NeverOverworldSculkOwnership.canSearchMovement") > patched_spreader.index("? getValidMovementPos"):
        fail("SELF-TEST: movement ownership check must happen before movement reads")
    print("[NeverFolia][NeverOverworld sculk] CHUNK OWNERSHIP SELF-TEST OK")


def apply(root: Path) -> None:
    paths = {
        "patch": root / PATCH_REL,
        "spreader": root / SPREADER_REL,
        "block": root / BLOCK_REL,
        "vein": root / VEIN_REL,
        "helper": root / HELPER_REL,
    }
    for label in ("patch", "spreader", "block", "vein"):
        if not paths[label].is_file():
            fail(f"{label} source not found: {paths[label]}")

    paths["patch"].write_text(patch_sculk_patch_feature(paths["patch"].read_text(encoding="utf-8")), encoding="utf-8")
    paths["spreader"].write_text(patch_sculk_spreader(paths["spreader"].read_text(encoding="utf-8")), encoding="utf-8")
    paths["block"].write_text(patch_sculk_block(paths["block"].read_text(encoding="utf-8")), encoding="utf-8")
    paths["vein"].write_text(patch_sculk_vein(paths["vein"].read_text(encoding="utf-8")), encoding="utf-8")
    paths["helper"].write_text(helper_source(), encoding="utf-8")

    print("[NeverFolia][NeverOverworld sculk] worldgen chunk-ownership hook applied")
    for label, path in paths.items():
        print(f"  {label}: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Make NR-DEV-1 sculk worldgen owner-chunk deterministic")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required unless --self-test is used")

    self_test()
    apply(args.folia.resolve())


if __name__ == "__main__":
    main()
