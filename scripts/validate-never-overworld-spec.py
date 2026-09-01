#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld spec] {message}")


def text(rel: str) -> str:
    path = ROOT / rel
    if not path.is_file():
        fail(f"missing required file: {rel}")
    return path.read_text(encoding="utf-8")


def require(source: str, needle: str, where: str) -> None:
    if needle not in source:
        fail(f"{where} missing required contract marker: {needle!r}")


def forbid(source: str, needle: str, where: str) -> None:
    if needle in source:
        fail(f"{where} contains obsolete/forbidden contract marker: {needle!r}")


def main() -> None:
    env = text("build.env")
    builder = text("scripts/build-never-overworld-core-pack.py")
    flood = text("scripts/apply-never-overworld-flood-hook.py")
    fingerprint = text("scripts/fingerprint-never-overworld-pack.py")
    guard = text("scripts/apply-never-overworld-fingerprint-guard.py")
    hasher = text("scripts/hash-never-overworld-generation-chunks.py")
    doc = text("docs/worldgen/never-overworld.md")

    require(env, "WORLDGEN_OVERWORLD=NR-DEV-1", "build.env")

    for marker in (
        'WORLDGEN_ID = "NR-DEV-1"',
        "DIM_MIN_Y = -512",
        "DIM_HEIGHT = 1024",
        "VANILLA_MIN_Y = -64",
        "DEEP_BLEND_START_Y = -96",
        "FLOOD_LEVEL = 128",
        '"terrain_mode": "VANILLA_FLOODED"',
        '"flood_phase": "neverfolia-light-barrier-surface-connected-chunk-owned-v3"',
        '"sealed_cavity_policy": "remain-dry-without-surface-connected-air-path"',
        "minecraft:lake_lava_underground",
        "minecraft:spring_water",
        "minecraft:spring_lava",
    ):
        require(builder, marker, "NeverOverworld Core builder")
    forbid(builder, "FULL_FLOOD_MIN_Y", "NeverOverworld Core builder")
    forbid(builder, '"full_flood_min_y"', "NeverOverworld Core builder")

    for marker in (
        "ChunkStatusTasks.java",
        "NeverOverworldFlood.apply(context.level(), chunk);",
        "beginning of the LIGHT chunk status",
        "EXPECTED_MIN_Y = -512",
        "EXPECTED_HEIGHT = 1024",
        "FLOOD_LEVEL = 128",
        "Level.OVERWORLD",
        "Heightmap.Types.OCEAN_FLOOR_WG",
        "section.hasFluid()",
        "floodSurfaceConnectedAir",
    ):
        require(flood, marker, "NeverOverworld flood hook")
    for obsolete in (
        "FULL_FLOOD_MIN_Y",
        "applyBiomeDecoration",
        "floodChunkLocalOceanConnections",
    ):
        forbid(flood, obsolete, "NeverOverworld flood hook")

    for marker in (
        'WORLDGEN_ID = "NR-DEV-1"',
        'ROOT_FINGERPRINT_ENTRY = "neveroverworld-worldgen-fingerprint.json"',
        'RESOURCE_FINGERPRINT_ENTRY = "data/neverfolia/neveroverworld/worldgen_fingerprint.json"',
        'ALGORITHM = "sha256-path-and-content-v1"',
    ):
        require(fingerprint, marker, "NeverOverworld fingerprint tool")

    for marker in (
        "NeverOverworldFingerprintGuard",
        "NR-DEV-1",
        "neveroverworld-worldgen-fingerprint.json",
        ".neverfolia-neveroverworld-worldgen.lock",
    ):
        require(guard, marker, "NeverOverworld fingerprint guard")

    for marker in (
        "BODY_SECTION_MIN = -32",
        "BODY_SECTION_MAX = 31",
        'ALGORITHM = "neveroverworld-generation-semantic-v1"',
        '"minecraft:water[level>0]": "minecraft:air"',
        '"minecraft:lava[level>0]": "minecraft:air"',
    ):
        require(hasher, marker, "NeverOverworld semantic hasher")

    for marker in (
        "# NeverOverworld — NR-DEV-1",
        "Minimum build/generation Y: `-512`",
        "Maximum build/generation Y: `511`",
        "Flood plane: `Y=128`",
        "Sealed caves",
        "strict chunk-order",
        ".neverfolia-neveroverworld-worldgen.lock",
    ):
        require(doc, marker, "NeverOverworld specification")

    dimension_height = re.search(r"^DIM_HEIGHT\s*=\s*(-?\d+)\s*$", builder, re.MULTILINE)
    dimension_min = re.search(r"^DIM_MIN_Y\s*=\s*(-?\d+)\s*$", builder, re.MULTILINE)
    if dimension_height is None or dimension_min is None:
        fail("cannot parse builder dimension constants")
    min_y = int(dimension_min.group(1))
    height = int(dimension_height.group(1))
    if min_y + height - 1 != 511:
        fail(f"builder dimension range drifted: min_y={min_y}, height={height}")

    print("[NeverFolia][NeverOverworld spec] NR-DEV-1 CONTRACT OK")
    print("  dimension: Y=-512..511 (1024)")
    print("  upper: vanilla 26.2 from Y>=-64")
    print("  flood: surface-connected to Y=128 at LIGHT barrier")
    print("  fingerprint: independent NR-DEV-1 lock")


if __name__ == "__main__":
    main()
