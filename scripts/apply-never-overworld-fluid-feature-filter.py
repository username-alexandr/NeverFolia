#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

GENERATOR_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/ChunkGenerator.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFluidFeatures.java")
HOOK_CALL = "NeverOverworldFluidFeatures.shouldSkip(level, featureRegistry, feature)"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld fluid features] {message}")


def patch_generator(source: str) -> str:
    if HOOK_CALL in source:
        fail("ChunkGenerator is already patched")

    # Insert after the concrete PlacedFeature is selected and before the supplier,
    # RNG seed and placeWithBiomeCheck call. Skipped entries keep their global
    # feature index, so every remaining vanilla feature retains its original seed.
    # The indent capture is intentionally [ \t]* rather than \s*: it must never
    # absorb a preceding newline/blank line into generated Java indentation.
    needle = re.compile(
        r"^(?P<indent>[ \t]*)PlacedFeature\s+feature\s*=\s*\(PlacedFeature\)stepFeatureData\.features\(\)\.get\(globalIndexOfFeature\);[ \t]*\n",
        re.MULTILINE,
    )
    matches = list(needle.finditer(source))
    if len(matches) != 1:
        fail(f"expected exactly one PlacedFeature selection point, got {len(matches)}")

    match = matches[0]
    indent = match.group("indent")
    insertion = (
        match.group(0)
        + f"{indent}if (NeverOverworldFluidFeatures.shouldSkip(level, featureRegistry, feature)) {{\n"
        + f"{indent}   continue;\n"
        + f"{indent}}}\n"
    )
    return source[: match.start()] + insertion + source[match.end() :]


def helper_source() -> str:
    return r'''package net.minecraft.world.level.chunk;

import com.mojang.logging.LogUtils;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import net.minecraft.core.Registry;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.WorldGenLevel;
import net.minecraft.world.level.levelgen.placement.PlacedFeature;
import org.slf4j.Logger;

/** Native generated-fluid feature policy for NR-DEV-1. */
final class NeverOverworldFluidFeatures {
    private static final Logger LOGGER = LogUtils.getLogger();
    private static final AtomicBoolean ANNOUNCED = new AtomicBoolean();
    private static final AtomicBoolean SKIP_ANNOUNCED = new AtomicBoolean();
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;
    private static final Set<String> BLOCKED = Set.of(
        "minecraft:lake_lava_underground",
        "minecraft:lake_lava_surface",
        "minecraft:spring_water",
        "minecraft:spring_lava",
        "minecraft:spring_lava_frozen"
    );

    private NeverOverworldFluidFeatures() {}

    static boolean shouldSkip(
        final WorldGenLevel level,
        final Registry<PlacedFeature> registry,
        final PlacedFeature feature
    ) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != EXPECTED_MIN_Y
            || level.getHeight() != EXPECTED_HEIGHT) {
            return false;
        }

        if (ANNOUNCED.compareAndSet(false, true)) {
            LOGGER.info(
                "[NeverFolia][NeverOverworld] Native generated-fluid feature filter active; blocked={}",
                BLOCKED
            );
        }

        return registry.getResourceKey(feature)
            .map(key -> {
                final String id = key.identifier().toString();
                final boolean blocked = BLOCKED.contains(id);
                if (blocked && SKIP_ANNOUNCED.compareAndSet(false, true)) {
                    LOGGER.info(
                        "[NeverFolia][NeverOverworld] Native generated-fluid feature filter skipped blocked feature={}",
                        id
                    );
                }
                return blocked;
            })
            .orElse(false);
    }
}
'''


def self_test() -> None:
    fixture = '''class ChunkGenerator {
   void decorate() {
      for (int featureIndex = 0; featureIndex < numberOfFeaturesInStep; featureIndex++) {
         int globalIndexOfFeature = indexArray[featureIndex];

         PlacedFeature feature = (PlacedFeature)stepFeatureData.features().get(globalIndexOfFeature);
         Supplier<String> currentlyGenerating = () -> feature.toString();
         random.setFeatureSeed(decorationSeed, globalIndexOfFeature, stepIndex);
         feature.placeWithBiomeCheck(level, this, random, origin);
      }
   }
}
'''
    patched = patch_generator(fixture)
    if patched.count(HOOK_CALL) != 1:
        fail("SELF-TEST: native fluid feature filter not injected exactly once")
    feature_line = patched.index("PlacedFeature feature")
    guard_line = patched.index(HOOK_CALL)
    seed_line = patched.index("random.setFeatureSeed")
    if not feature_line < guard_line < seed_line:
        fail("SELF-TEST: guard must run after feature selection and before RNG seed")
    guard_source_line = next(line for line in patched.splitlines() if HOOK_CALL in line)
    if not guard_source_line.startswith("         if ("):
        fail(f"SELF-TEST: guard indentation drifted across line boundaries: {guard_source_line!r}")

    helper = helper_source()
    for marker in (
        "LogUtils.getLogger()",
        "AtomicBoolean ANNOUNCED",
        "AtomicBoolean SKIP_ANNOUNCED",
        "ANNOUNCED.compareAndSet(false, true)",
        "SKIP_ANNOUNCED.compareAndSet(false, true)",
        "Native generated-fluid feature filter active; blocked={}",
        "Native generated-fluid feature filter skipped blocked feature={}",
        "EXPECTED_MIN_Y = -512",
        "EXPECTED_HEIGHT = 1024",
        "Level.OVERWORLD",
        "minecraft:lake_lava_underground",
        "minecraft:lake_lava_surface",
        "minecraft:spring_water",
        "minecraft:spring_lava",
        "minecraft:spring_lava_frozen",
        "key.identifier().toString()",
    ):
        if marker not in helper:
            fail(f"SELF-TEST: helper missing {marker!r}")

    print("[NeverFolia][NeverOverworld fluid features] NATIVE FILTER SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply native NR-DEV-1 generated-fluid feature filter")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required unless --self-test is used")

    folia = args.folia.resolve()
    generator = folia / GENERATOR_REL
    helper = folia / HELPER_REL
    if not generator.is_file():
        fail(f"ChunkGenerator source not found: {generator}")

    generator.write_text(patch_generator(generator.read_text(encoding="utf-8")), encoding="utf-8")
    helper.write_text(helper_source(), encoding="utf-8")

    print("[NeverFolia][NeverOverworld fluid features] native filter applied")
    print(f"  generator: {generator}")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
