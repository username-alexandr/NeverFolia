#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

GENERATOR_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/NoiseBasedChunkGenerator.java")
HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/NeverOverworldFluidPicker.java")
HOOK_CALL = "NeverOverworldFluidPicker.create(settings)"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld fluid] {message}")


def patch_generator(source: str) -> str:
    if HOOK_CALL in source:
        fail("NoiseBasedChunkGenerator is already patched")

    match = re.search(
        r"private\s+static\s+Aquifer\.FluidPicker\s+createFluidPicker\s*\(\s*final\s+NoiseGeneratorSettings\s+settings\s*\)\s*\{",
        source,
        re.DOTALL,
    )
    if match is None:
        fail("NoiseBasedChunkGenerator.createFluidPicker(...) not found")

    open_brace = source.find("{", match.start(), match.end())
    if open_brace < 0:
        fail("createFluidPicker opening brace not found")

    injection = (
        "\n      // NeverFolia: NR-DEV-1 owns the deep aquifer policy. Preserve the\n"
        "      // normal upper water aquifer, but never manufacture the vanilla lava\n"
        "      // aquifer below Y=-54 in the extended NeverOverworld generator.\n"
        "      if (NeverOverworldFluidPicker.matches(settings)) {\n"
        "         return NeverOverworldFluidPicker.create(settings);\n"
        "      }\n"
    )
    return source[: open_brace + 1] + injection + source[open_brace + 1 :]


def helper_source() -> str:
    return r'''package net.minecraft.world.level.levelgen;

import com.mojang.logging.LogUtils;
import net.minecraft.SharedConstants;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.dimension.DimensionType;
import org.slf4j.Logger;

/**
 * Native NR-DEV-1 aquifer policy.
 *
 * <p>The vanilla Overworld fluid picker returns lava below Y=-54. NeverRaft has
 * an extended world floor at Y=-512, so that rule would create hundreds of blocks
 * of lava-bearing aquifer space. NR-DEV-1 instead returns AIR in the deep branch.
 * The ordinary upper water branch is retained for vanilla-compatible feature
 * generation; the later NeverOverworld flood pass normalizes final connectivity.</p>
 */
final class NeverOverworldFluidPicker {
    private static final Logger LOGGER = LogUtils.getLogger();
    private static final int EXPECTED_MIN_Y = -512;
    private static final int EXPECTED_HEIGHT = 1024;

    private NeverOverworldFluidPicker() {}

    static boolean matches(final NoiseGeneratorSettings settings) {
        final NoiseSettings noise = settings.noiseSettings();
        return noise.minY() == EXPECTED_MIN_Y
            && noise.height() == EXPECTED_HEIGHT
            && settings.defaultFluid().is(Blocks.WATER);
    }

    static Aquifer.FluidPicker create(final NoiseGeneratorSettings settings) {
        final int seaLevel = settings.seaLevel();
        final int deepCutoff = Math.min(-54, seaLevel);
        final Aquifer.FluidStatus seaStatus = new Aquifer.FluidStatus(seaLevel, settings.defaultFluid());
        final BlockState air = Blocks.AIR.defaultBlockState();
        final Aquifer.FluidStatus emptyStatus = new Aquifer.FluidStatus(DimensionType.MIN_Y * 2, air);

        LOGGER.info(
            "[NeverFolia][NeverOverworld] Native fluid picker active: lava aquifer disabled; minY={} height={} seaLevel={} deepCutoff={}",
            EXPECTED_MIN_Y,
            EXPECTED_HEIGHT,
            seaLevel,
            deepCutoff
        );

        return (x, y, z) -> {
            if (SharedConstants.DEBUG_DISABLE_FLUID_GENERATION) {
                return emptyStatus;
            }
            // Vanilla would return a LAVA FluidStatus here. NR-DEV-1 deliberately
            // returns AIR, so lava cannot originate from the global aquifer picker.
            return y < deepCutoff ? emptyStatus : seaStatus;
        };
    }
}
'''


def self_test() -> None:
    fixture = '''package net.minecraft.world.level.levelgen;
class NoiseBasedChunkGenerator {
   private static Aquifer.FluidPicker createFluidPicker(final NoiseGeneratorSettings settings) {
      Aquifer.FluidStatus lavaStatus = null;
      return null;
   }
}
'''
    patched = patch_generator(fixture)
    if patched.count("NeverOverworldFluidPicker.matches(settings)") != 1:
        fail("SELF-TEST: matches hook not injected exactly once")
    if patched.count(HOOK_CALL) != 1:
        fail("SELF-TEST: native picker call not injected exactly once")

    helper = helper_source()
    for marker in (
        "EXPECTED_MIN_Y = -512",
        "EXPECTED_HEIGHT = 1024",
        "settings.defaultFluid().is(Blocks.WATER)",
        "Math.min(-54, seaLevel)",
        "return y < deepCutoff ? emptyStatus : seaStatus",
        "Native fluid picker active: lava aquifer disabled",
    ):
        if marker not in helper:
            fail(f"SELF-TEST: helper missing {marker!r}")
    if "Blocks.LAVA" in helper:
        fail("SELF-TEST: native NR fluid helper must not construct lava")

    print("[NeverFolia][NeverOverworld fluid] NATIVE PICKER SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply native NR-DEV-1 lava-free aquifer picker")
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
        fail(f"NoiseBasedChunkGenerator source not found: {generator}")

    source = generator.read_text(encoding="utf-8")
    generator.write_text(patch_generator(source), encoding="utf-8")
    helper.write_text(helper_source(), encoding="utf-8")

    print("[NeverFolia][NeverOverworld fluid] native lava-free picker applied")
    print(f"  generator: {generator}")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
