#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

HELPER_REL = Path(
    "folia-server/src/minecraft/java/net/minecraft/world/level/levelgen/structure/structures/NeverNetherStructurePlacement.java"
)


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverNether placement debug] {message}")


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        fail(f"expected exactly one {label} marker, got {count}")
    return source.replace(old, new, 1)


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: instrument-never-nether-placement-debug.py /path/to/.work/Folia")

    folia = Path(sys.argv[1]).resolve()
    helper = folia / HELPER_REL
    if not helper.is_file():
        fail(f"placement helper not found: {helper}")

    source = helper.read_text(encoding="utf-8")
    if "neverfolia.nevernether.debugPlacement" in source:
        fail("placement helper is already instrumented")

    source = replace_once(
        source,
        "    private static final int MIN_CLEARANCE = 8;\n",
        "    private static final int MIN_CLEARANCE = 8;\n"
        "    private static final boolean DEBUG_PLACEMENT = Boolean.getBoolean(\"neverfolia.nevernether.debugPlacement\");\n"
        "    private static final System.Logger DEBUG_LOGGER = System.getLogger(\"NeverFolia-NeverNether-Placement\");\n",
        "debug constants",
    )

    source = replace_once(
        source,
        "        if (profile.mode == Mode.LAVA_BASIN) {\n"
        "            if (profile.requireLargeLavaBasin && !hasLargeLavaBasin(context, anchorX, anchorZ)) {\n"
        "                return REJECT_Y;\n"
        "            }\n"
        "            final int lavaFloor = findLavaFloor(context, anchorX, anchorZ, profile);\n"
        "            return isSafe(lavaFloor) ? lavaFloor : REJECT_Y;\n"
        "        }\n",
        "        if (profile.mode == Mode.LAVA_BASIN) {\n"
        "            if (profile.requireLargeLavaBasin && !hasLargeLavaBasin(context, anchorX, anchorZ)) {\n"
        "                debugDecision(poolId, profile, chunkX, chunkZ, REJECT_Y, \"lava_basin_too_small\");\n"
        "                return REJECT_Y;\n"
        "            }\n"
        "            final int lavaFloor = findLavaFloor(context, anchorX, anchorZ, profile);\n"
        "            if (!isSafe(lavaFloor)) {\n"
        "                debugDecision(poolId, profile, chunkX, chunkZ, REJECT_Y, \"lava_floor_not_found_or_unsafe\");\n"
        "                return REJECT_Y;\n"
        "            }\n"
        "            debugDecision(poolId, profile, chunkX, chunkZ, lavaFloor, \"lava_basin_floor\");\n"
        "            return lavaFloor;\n"
        "        }\n",
        "lava decision",
    )

    source = replace_once(
        source,
        "        int y = chooseCavernFloor(column, profile.preferredMinY, profile.preferredMaxY, hash);\n"
        "        if (y == REJECT_Y) {\n"
        "            y = chooseCavernFloor(column, profile.hardMinY, profile.hardMaxY, mix64(hash));\n"
        "        }\n"
        "        return isSafe(y) ? y : REJECT_Y;\n"
        "    }\n",
        "        int y = chooseCavernFloor(column, profile.preferredMinY, profile.preferredMaxY, hash);\n"
        "        String decisionReason = \"preferred_band\";\n"
        "        if (y == REJECT_Y) {\n"
        "            y = chooseCavernFloor(column, profile.hardMinY, profile.hardMaxY, mix64(hash));\n"
        "            decisionReason = \"hard_band_fallback\";\n"
        "        }\n"
        "        if (!isSafe(y)) {\n"
        "            debugDecision(poolId, profile, chunkX, chunkZ, REJECT_Y, \"no_cavern_floor\");\n"
        "            return REJECT_Y;\n"
        "        }\n"
        "        debugDecision(poolId, profile, chunkX, chunkZ, y, decisionReason);\n"
        "        return y;\n"
        "    }\n",
        "cavern decision",
    )

    source = replace_once(
        source,
        "    private static boolean isLava(BlockState state) {\n",
        "    private static void debugDecision(\n"
        "        String poolId,\n"
        "        Profile profile,\n"
        "        int chunkX,\n"
        "        int chunkZ,\n"
        "        int y,\n"
        "        String reason\n"
        "    ) {\n"
        "        if (!DEBUG_PLACEMENT) {\n"
        "            return;\n"
        "        }\n"
        "        final String result = y == REJECT_Y ? \"REJECT\" : Integer.toString(y);\n"
        "        DEBUG_LOGGER.log(\n"
        "            System.Logger.Level.INFO,\n"
        "            \"[NeverNetherPlacement] pool={0} profile={1} mode={2} chunk={3},{4} result={5} reason={6}\",\n"
        "            poolId, profile.name(), profile.mode(), chunkX, chunkZ, result, reason\n"
        "        );\n"
        "    }\n\n"
        "    private static boolean isLava(BlockState state) {\n",
        "debug helper insertion",
    )

    helper.write_text(source, encoding="utf-8")
    print("[NeverFolia][NeverNether placement debug] instrumentation applied")
    print(f"  helper: {helper}")
    print("  enable with: -Dneverfolia.nevernether.debugPlacement=true")


if __name__ == "__main__":
    main()
