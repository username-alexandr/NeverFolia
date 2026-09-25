#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

GENERATOR_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/ChunkGenerator.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFluidFeatures.java")
HOOK_PREFIX = "NeverOverworldFluidFeatures.shouldSkip("
IDENT = r"[A-Za-z_$][A-Za-z0-9_$]*"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld fluid features] {message}")


def find_injection_site(source: str):
    # Mojang-mapped local names are not an API. Match the semantic shape instead:
    # a PlacedFeature loaded from StepFeatureData.features().get(...), followed by
    # registry key lookup and placeWithBiomeCheck for that same local variable.
    selection = re.compile(
        rf"^(?P<indent>[ \t]*)PlacedFeature\s+(?P<feature>{IDENT})\s*=\s*"
        rf"(?:\(PlacedFeature\)\s*)?(?P<step>{IDENT})\.features\(\)\.get\((?P<index>[^;\n]+)\);[ \t]*\n",
        re.MULTILINE,
    )

    resolved = []
    raw = list(selection.finditer(source))
    for match in raw:
        feature = match.group("feature")
        window = source[match.end() : match.end() + 3000]

        registry_match = re.search(
            rf"\b(?P<registry>{IDENT})\.getResourceKey\(\s*{re.escape(feature)}\s*\)",
            window,
        )
        place_match = re.search(
            rf"\b{re.escape(feature)}\.placeWithBiomeCheck\(\s*(?P<level>{IDENT})\s*,",
            window,
        )
        if registry_match is None or place_match is None:
            continue
        resolved.append(
            (
                match,
                feature,
                registry_match.group("registry"),
                place_match.group("level"),
            )
        )

    if len(resolved) != 1:
        samples = []
        for match in raw[:5]:
            line_no = source.count("\n", 0, match.start()) + 1
            samples.append(
                f"line {line_no}: feature={match.group('feature')} step={match.group('step')} index={match.group('index').strip()}"
            )
        detail = "; ".join(samples) if samples else "no PlacedFeature-from-features().get(...) candidates"
        fail(
            "expected exactly one decoration PlacedFeature selection point, "
            f"resolved={len(resolved)} raw={len(raw)}; {detail}"
        )
    return resolved[0]


def patch_generator(source: str) -> str:
    if HOOK_PREFIX in source:
        fail("ChunkGenerator is already patched")

    match, feature, registry, level = find_injection_site(source)
    indent = match.group("indent")
    hook = f"NeverOverworldFluidFeatures.shouldSkip({level}, {registry}, {feature})"
    insertion = (
        match.group(0)
        + f"{indent}if ({hook}) {{\n"
        + f"{indent}   continue;\n"
        + f"{indent}}}\n"
    )
    patched = source[: match.start()] + insertion + source[match.end() :]
    if patched.count(HOOK_PREFIX) != 1:
        fail("native fluid feature hook was not injected exactly once")
    return patched


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
    fixtures = [
        (
            '''class ChunkGenerator {
   void decorate() {
      Registry<PlacedFeature> featureRegistry = null;
      for (int featureIndex = 0; featureIndex < numberOfFeaturesInStep; featureIndex++) {
         int globalIndexOfFeature = indexArray[featureIndex];

         PlacedFeature feature = (PlacedFeature)stepFeatureData.features().get(globalIndexOfFeature);
         Supplier<String> currentlyGenerating = () -> featureRegistry.getResourceKey(feature).toString();
         random.setFeatureSeed(decorationSeed, globalIndexOfFeature, stepIndex);
         feature.placeWithBiomeCheck(level, this, random, origin);
      }
   }
}
''',
            "NeverOverworldFluidFeatures.shouldSkip(level, featureRegistry, feature)",
        ),
        (
            '''class ChunkGenerator {
   void decorate() {
      Registry<PlacedFeature> registry3 = null;
      for (int k = 0; k < count; ++k) {
         int l = mapping[k];
         PlacedFeature placedFeature = stepData.features().get(l);
         Supplier<String> supplier = () -> registry3.getResourceKey(placedFeature).toString();
         random.setFeatureSeed(seed, l, i);
         placedFeature.placeWithBiomeCheck(worldGenLevel, this, random, origin);
      }
   }
}
''',
            "NeverOverworldFluidFeatures.shouldSkip(worldGenLevel, registry3, placedFeature)",
        ),
    ]

    for fixture, expected_hook in fixtures:
        patched = patch_generator(fixture)
        if patched.count(HOOK_PREFIX) != 1 or expected_hook not in patched:
            fail(f"SELF-TEST: expected semantic hook missing: {expected_hook}")
        feature_line = patched.index("PlacedFeature ")
        guard_line = patched.index(HOOK_PREFIX)
        seed_line = patched.index("setFeatureSeed")
        if not feature_line < guard_line < seed_line:
            fail("SELF-TEST: guard must run after feature selection and before RNG seed")
        guard_source_line = next(line for line in patched.splitlines() if HOOK_PREFIX in line)
        if not guard_source_line.startswith("         if ("):
            fail(f"SELF-TEST: guard indentation drifted: {guard_source_line!r}")

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
