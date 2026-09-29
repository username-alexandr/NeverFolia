#!/usr/bin/env python3
"""Install the R399 bounded ocean-closure pass into a materialized Folia tree.

R39.24 integrates the previously field-tested R399 LIGHT-stage closure into the
normal NeverFolia build. The owning chunk is the only writer. A completed
FEATURES radius-3 halo is required before LIGHT. Synthetic AIR->WATER writes are
handled by NeverOverworldOceanClosureR399 and are strictly below Y=128.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JAVA = Path("folia-server/src/minecraft/java")
CHUNK = JAVA / "net/minecraft/world/level/chunk"
LIGHT = JAVA / "ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask.java"
PYRAMID = JAVA / "net/minecraft/world/level/chunk/status/ChunkPyramid.java"

LIGHT_HOOK = "                net.minecraft.world.level.chunk.NeverOverworldOceanClosureR399.apply(task.world, task.neverOverworldNeighbours, task.fromChunk); // R399_OCEAN_CLOSURE"
LIGHT_ANCHOR = "                net.minecraft.world.level.chunk.NeverOverworldWaterAuditR38.end(task.world, task.fromChunk, waterAuditR38);"
PYRAMID_OLD = ".step(ChunkStatus.LIGHT, s -> s.addRequirement(ChunkStatus.INITIALIZE_LIGHT, 1).setTask(ChunkStatusTasks::light))"
PYRAMID_NEW = ".step(ChunkStatus.LIGHT, s -> s.addRequirement(ChunkStatus.INITIALIZE_LIGHT, 3).addRequirement(ChunkStatus.FEATURES, 3).setTask(ChunkStatusTasks::light))"

def fail(msg: str) -> None:
    raise ValueError("[R399-INTEGRATION] " + msg)

def expected_sources() -> dict[str, str]:
    out = {}
    for name in ("NeverOverworldOceanClosureR399.java", "OceanConnectivityR399.java"):
        p = ROOT / "native/overworld-r399" / name
        if not p.is_file():
            fail("missing source " + str(p))
        out[name] = p.read_text(encoding="utf-8")
    return out

def prepare(folia: Path) -> dict[Path, str]:
    staged: dict[Path, str] = {}
    sources = expected_sources()
    for name, text in sources.items():
        staged[folia / CHUNK / name] = text

    light_path = folia / LIGHT
    pyramid_path = folia / PYRAMID
    if not light_path.is_file() or not pyramid_path.is_file():
        fail("materialized LIGHT/ChunkPyramid source missing")

    light = light_path.read_text(encoding="utf-8")
    if LIGHT_HOOK not in light:
        if light.count(LIGHT_ANCHOR) != 1:
            fail("R38 LIGHT anchor missing/ambiguous")
        light = light.replace(LIGHT_ANCHOR, LIGHT_HOOK + "\n" + LIGHT_ANCHOR, 1)
    if light.count(LIGHT_HOOK) != 1:
        fail("R399 LIGHT hook missing/duplicated")
    staged[light_path] = light

    pyramid = pyramid_path.read_text(encoding="utf-8")
    if PYRAMID_NEW not in pyramid:
        if pyramid.count(PYRAMID_OLD) != 1:
            fail("LIGHT pyramid anchor missing/ambiguous")
        pyramid = pyramid.replace(PYRAMID_OLD, PYRAMID_NEW, 1)
    if pyramid.count(PYRAMID_NEW) != 1:
        fail("R399 FEATURES radius-3 dependency missing/duplicated")
    staged[pyramid_path] = pyramid
    return staged

def verify(folia: Path, staged: dict[Path, str]) -> None:
    sources = expected_sources()
    for name, expected in sources.items():
        path = folia / CHUNK / name
        actual = staged.get(path, path.read_text(encoding="utf-8") if path.is_file() else "")
        if actual != expected:
            fail("materialized source differs: " + name)
    light_path = folia / LIGHT
    pyramid_path = folia / PYRAMID
    light = staged.get(light_path, light_path.read_text(encoding="utf-8"))
    pyramid = staged.get(pyramid_path, pyramid_path.read_text(encoding="utf-8"))
    if light.count(LIGHT_HOOK) != 1:
        fail("LIGHT hook invariant failed")
    if pyramid.count(PYRAMID_NEW) != 1:
        fail("pyramid dependency invariant failed")
    closure = sources["NeverOverworldOceanClosureR399.java"]
    if "y>=WATER_SURFACE_Y" not in closure or "WATER_SURFACE_Y=128" not in closure:
        fail("R39.24 Y>=128 surface gate missing")

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia", type=Path)
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args()
    folia = a.folia.resolve()
    staged = prepare(folia)
    verify(folia, staged)
    if not a.check_only:
        for path, text in staged.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    print("[R399-INTEGRATION] bounded ocean closure + Y<128 surface gate + LIGHT radius3/FEATURES radius3 OK")

if __name__ == "__main__":
    main()
