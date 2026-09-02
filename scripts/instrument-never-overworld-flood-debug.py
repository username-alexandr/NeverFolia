#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")
MARKER = "[NeverFolia][NeverOverworld] LIGHT flood active: chunk-owned surface-connected Y<=128"
PROBE_MARKER = "[NeverFolia][NeverOverworld] LIGHT flood probe:"
EXPECTED_JAVA_BLOCK = (
    "        if (ACTIVATION_LOGGED.compareAndSet(false, true)) {\n"
    '            LOGGER.info("[NeverFolia][NeverOverworld] LIGHT flood active: chunk-owned surface-connected Y<=128");\n'
    "        }\n"
    "\n"
    "        final int minY = level.getMinY() + 1;\n"
)
PROBE_JAVA_BLOCK = (
    "        final int neverOverworldProbeIndex = PROBE_LOG_COUNT.getAndIncrement();\n"
    "        if (neverOverworldProbeIndex < 12) {\n"
    '            LOGGER.info("[NeverFolia][NeverOverworld] LIGHT flood probe: dimension={} minY={} height={} chunk={}",\n'
    "                level.getLevel().dimension(), level.getMinY(), level.getHeight(), chunk.getPos());\n"
    "        }\n"
    "\n"
)


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld flood debug] {message}")


def instrument(source: str) -> str:
    if MARKER in source or PROBE_MARKER in source:
        fail("flood helper is already instrumented")

    import_anchor = "import net.minecraft.core.BlockPos;\n"
    if source.count(import_anchor) != 1:
        fail("expected exactly one BlockPos import anchor")
    source = source.replace(
        import_anchor,
        "import com.mojang.logging.LogUtils;\n"
        "import java.util.concurrent.atomic.AtomicBoolean;\n"
        "import java.util.concurrent.atomic.AtomicInteger;\n"
        + import_anchor,
        1,
    )

    logger_import_anchor = "import net.minecraft.world.level.levelgen.Heightmap;\n"
    if source.count(logger_import_anchor) != 1:
        fail("expected exactly one Heightmap import anchor")
    source = source.replace(
        logger_import_anchor,
        logger_import_anchor + "import org.slf4j.Logger;\n",
        1,
    )

    class_anchor = "public final class NeverOverworldFlood {\n"
    if source.count(class_anchor) != 1:
        fail("expected exactly one NeverOverworldFlood class anchor")
    source = source.replace(
        class_anchor,
        class_anchor
        + "    private static final Logger LOGGER = LogUtils.getLogger();\n"
        + "    private static final AtomicBoolean ACTIVATION_LOGGED = new AtomicBoolean();\n"
        + "    private static final AtomicInteger PROBE_LOG_COUNT = new AtomicInteger();\n",
        1,
    )

    apply_method_anchor = "    public static void apply(final WorldGenLevel level, final ChunkAccess chunk) {\n"
    if source.count(apply_method_anchor) != 1:
        fail("expected exactly one apply() method anchor")
    source = source.replace(
        apply_method_anchor,
        apply_method_anchor + PROBE_JAVA_BLOCK,
        1,
    )

    apply_anchor = "        final int minY = level.getMinY() + 1;\n"
    if source.count(apply_anchor) != 1:
        fail("expected exactly one apply() minY anchor")
    source = source.replace(apply_anchor, EXPECTED_JAVA_BLOCK, 1)
    return source


def self_test() -> None:
    fixture = '''package net.minecraft.world.level.chunk;

import net.minecraft.core.BlockPos;
import net.minecraft.world.level.levelgen.Heightmap;

public final class NeverOverworldFlood {
    private static final int EXPECTED_MIN_Y = -512;
    private NeverOverworldFlood() {}

    public static void apply(final WorldGenLevel level, final ChunkAccess chunk) {
        if (level.getMinY() != EXPECTED_MIN_Y) {
            return;
        }

        final int minY = level.getMinY() + 1;
    }
}
'''
    patched = instrument(fixture)
    for required in (
        "import com.mojang.logging.LogUtils;",
        "import java.util.concurrent.atomic.AtomicBoolean;",
        "import java.util.concurrent.atomic.AtomicInteger;",
        "import org.slf4j.Logger;",
        "AtomicBoolean ACTIVATION_LOGGED",
        "AtomicInteger PROBE_LOG_COUNT",
        PROBE_JAVA_BLOCK,
        EXPECTED_JAVA_BLOCK,
    ):
        if required not in patched:
            fail(f"SELF-TEST: missing {required!r}")

    if patched.count(MARKER) != 1:
        fail(f"SELF-TEST: expected exactly one runtime marker, got {patched.count(MARKER)}")
    if patched.count(PROBE_MARKER) != 1:
        fail(f"SELF-TEST: expected exactly one probe marker, got {patched.count(PROBE_MARKER)}")
    if patched.index("LIGHT flood probe:") > patched.index("if (level.getMinY()"):
        fail("SELF-TEST: LIGHT probe must execute before the NR height guard")
    if patched.index("ACTIVATION_LOGGED.compareAndSet") > patched.index("final int minY"):
        fail("SELF-TEST: activation marker must run before flood mutation work")

    # Regression guard for heavy #97: the old Python replacement accidentally
    # emitted Python string-literal fragments directly into the generated Java.
    for line in patched.splitlines():
        if line.lstrip().startswith('"'):
            fail(f"SELF-TEST: generated Java contains a stray quoted fragment: {line!r}")
    for forbidden in (
        '"            LOGGER.info(',
        '"        final int minY',
        '"        }',
    ):
        if forbidden in patched:
            fail(f"SELF-TEST: generated Java contains Python string fragment {forbidden!r}")

    print("[NeverFolia][NeverOverworld flood debug] RUNTIME-CONTEXT PROBE SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Instrument NR-DEV-1 LIGHT flood activation")
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path is required unless --self-test is used")

    helper = args.folia.resolve() / HELPER_REL
    if not helper.is_file():
        fail(f"flood helper not found: {helper}")
    helper.write_text(instrument(helper.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][NeverOverworld flood debug] activation marker + runtime context probe instrumented")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
