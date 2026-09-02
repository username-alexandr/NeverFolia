#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")
MARKER = "[NeverFolia][NeverOverworld] LIGHT flood active: chunk-owned surface-connected Y<=128"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld flood debug] {message}")


def instrument(source: str) -> str:
    if MARKER in source:
        fail("flood helper is already instrumented")

    import_anchor = "import net.minecraft.core.BlockPos;\n"
    if source.count(import_anchor) != 1:
        fail("expected exactly one BlockPos import anchor")
    source = source.replace(
        import_anchor,
        "import com.mojang.logging.LogUtils;\n"
        "import java.util.concurrent.atomic.AtomicBoolean;\n"
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
        + "    private static final AtomicBoolean ACTIVATION_LOGGED = new AtomicBoolean();\n",
        1,
    )

    apply_anchor = """        final int minY = level.getMinY() + 1;\n"""
    if source.count(apply_anchor) != 1:
        fail("expected exactly one apply() minY anchor")
    source = source.replace(
        apply_anchor,
        """        if (ACTIVATION_LOGGED.compareAndSet(false, true)) {\n"
        "            LOGGER.info(\"[NeverFolia][NeverOverworld] LIGHT flood active: chunk-owned surface-connected Y<=128\");\n"
        "        }\n\n"
        "        final int minY = level.getMinY() + 1;\n""",
        1,
    )
    return source


def self_test() -> None:
    fixture = '''package net.minecraft.world.level.chunk;\n\nimport net.minecraft.core.BlockPos;\nimport net.minecraft.world.level.levelgen.Heightmap;\n\npublic final class NeverOverworldFlood {\n    private static final int EXPECTED_MIN_Y = -512;\n    private NeverOverworldFlood() {}\n\n    public static void apply(final WorldGenLevel level, final ChunkAccess chunk) {\n        if (level.getMinY() != EXPECTED_MIN_Y) {\n            return;\n        }\n\n        final int minY = level.getMinY() + 1;\n    }\n}\n'''
    patched = instrument(fixture)
    for required in (
        "import com.mojang.logging.LogUtils;",
        "import java.util.concurrent.atomic.AtomicBoolean;",
        "import org.slf4j.Logger;",
        "AtomicBoolean ACTIVATION_LOGGED",
        "ACTIVATION_LOGGED.compareAndSet(false, true)",
        MARKER,
    ):
        if required not in patched:
            fail(f"SELF-TEST: missing {required!r}")
    if patched.index("ACTIVATION_LOGGED.compareAndSet") > patched.index("final int minY"):
        fail("SELF-TEST: activation marker must run before flood mutation work")
    print("[NeverFolia][NeverOverworld flood debug] SELF-TEST OK")


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
    print("[NeverFolia][NeverOverworld flood debug] activation marker instrumented")
    print(f"  helper: {helper}")


if __name__ == "__main__":
    main()
