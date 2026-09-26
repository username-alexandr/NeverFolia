#!/usr/bin/env python3
"""NeverOverworld FIELD-R21 unified fixpack.

Extends FIELD-R20 with cache-aware horizontal seam reconciliation while keeping
R19 external Overworld structures/island admission and R20 village hardening.
"""
from __future__ import annotations

import argparse
import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = "NO-FIELD-R21-FIXPACK-1"
JAVA = Path("folia-server/src/minecraft/java")
FLOOD = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFlood.java"
FLOOD15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"
TASKS = JAVA / "net/minecraft/world/level/chunk/status/ChunkStatusTasks.java"
MOONRISE = JAVA / "ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask.java"
SCHEDULER = JAVA / "ca/spottedleaf/moonrise/patches/chunk_system/scheduling/ChunkTaskScheduler.java"
SAFETY = JAVA / "net/minecraft/world/level/chunk/NeverOverworldGeneratedVillageSafety.java"
R19 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldExternalStructurePolicyR19.java"

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[NeverOverworld R21] " + message)

def verify(folia: Path) -> None:
    owner_flood = (folia / FLOOD).read_text(encoding="utf-8")
    flood = (folia / FLOOD15).read_text(encoding="utf-8")
    tasks = (folia / TASKS).read_text(encoding="utf-8")
    moonrise = (folia / MOONRISE).read_text(encoding="utf-8")
    scheduler = (folia / SCHEDULER).read_text(encoding="utf-8")
    safety = (folia / SAFETY).read_text(encoding="utf-8")
    r19 = (folia / R19).read_text(encoding="utf-8")

    require(owner_flood.count("public static void reweatherSubmergedSurface(") == 1,
            "R21 post-seam weathering entry point missing or duplicated")
    require("weatherSubmergedSurface(chunk, level.getMinY() + 1, FLOOD_LEVEL);" in owner_flood,
            "R21 post-seam weathering must reuse the canonical drowned-surface pass")
    require("reconcileSeams" in flood and "oceanConnectedFloodable" in flood,
            "R21 cache-aware flood helper missing")
    require("reconcileSeams(final WorldGenLevel level" in flood,
            "R21 seam reconciliation must receive world scope")
    require("getChunkIfPresent(ChunkStatus.FEATURES)" in flood,
            "R21 must read only already-present FEATURES neighbours")
    require("scan(chunk,visited,queue,x,y,z,minY,maxY,externalSeeds,allowSeams)" in flood,
            "R21 component scan must receive external seam seeds")
    require("boolean[] externalSeeds,boolean allowSeams" in flood,
            "R21 component scan seam parameters missing")
    require(
        "if (!traversable(chunk, pos)) return tailIn;" in flood
        or "if (!traversable(chunk, pos) || !customOceanColumnOpen(chunk, pos, y)) return tailIn;" in flood
        or "if (!traversable(chunk, pos) || (!chunk.getBlockState(pos).is(Blocks.WATER) && !customOceanColumnOpen(chunk, pos, y))) return tailIn;" in flood,
        "R21 neighbour ocean connectivity must traverse only eligible floodable volume"
    )
    require("getChunk(" not in flood and "level.getBlockState(" not in flood,
            "R21 flood helper must not synchronously load/read neighbours through level")

    owner = "net.minecraft.world.level.chunk.NeverOverworldFlood.apply(task.world, task.fromChunk);"
    reconcile = ("net.minecraft.world.level.chunk.NeverOverworldFloodConnectivityR15."
                 "reconcileSeams(task.world, task.neverOverworldNeighbours, task.fromChunk);")
    reweather = "net.minecraft.world.level.chunk.NeverOverworldFlood.reweatherSubmergedSurface(task.world, task.fromChunk);"
    ecology13 = "net.minecraft.world.level.chunk.NeverOverworldEcologyR13.cleanup(task.world, task.fromChunk);"
    ecology15 = "net.minecraft.world.level.chunk.NeverOverworldEcologyR15.cleanup(task.world, task.fromChunk);"
    require("NeverOverworldFlood.apply(" not in tasks
            and "NeverOverworldFloodConnectivityR15.reconcileSeams(" not in tasks,
            "bypassed ChunkStatusTasks must not own R21 runtime flood")
    require(moonrise.count(owner) == 1 and moonrise.count(reconcile) == 1,
            "R21 Moonrise owner/reconcile hook missing or duplicated")
    require(moonrise.count(reweather) == 1,
            "R21 post-seam drowned-surface weathering missing or duplicated")
    require(moonrise.count(ecology13) == 1 and moonrise.count(ecology15) == 1,
            "R21 post-seam ecology cleanup missing or duplicated")
    require(moonrise.find(owner) < moonrise.find(reconcile)
            < moonrise.find(reweather)
            < moonrise.find(ecology13) < moonrise.find(ecology15)
            < moonrise.find("StarLightEngine.getEmptySectionsForChunk"),
            "R21 Moonrise runtime order is not owner flood -> reconcile -> weathering -> ecology -> Starlight")
    require("StaticCache2D<GenerationChunkHolder> neverOverworldNeighbours" in moonrise,
            "R21 Moonrise neighbour cache field missing")
    require("new ChunkLightTask(this, this.world, chunkX, chunkZ, chunk, neighbours, initialPriority)" in scheduler,
            "R21 scheduler does not pass LIGHT neighbour cache")

    require("MAX_PIECE_SURFACE_SPAN = 8" in safety,
            "R20 village slope hardening missing")
    require(r19.count('case "') == 134,
            "R19 external surface structure table changed")
    require("MIN_DRY_SURFACE_Y = 129" in r19,
            "R19 island admission changed")

    print(f"[NeverOverworld R21] {PROFILE} final invariants OK")

def apply(folia: Path) -> None:
    r20 = [sys.executable, str(ROOT / "scripts/apply-never-overworld-fixpack-r20.py"), str(folia)]
    checked = subprocess.run(r20 + ["--check-only"], cwd=ROOT, check=False)
    if checked.returncode != 0:
        # The post-patch chain can leave a known partial R21 state: the
        # reweather entry point exists in NeverOverworldFlood, while the
        # R15/R20 helper graph has not been materialized yet. Normalize only
        # that exact R21-owned method before replaying the guarded R13..R20
        # chain; unknown input states still fail their SHA contracts.
        flood15 = folia / FLOOD15
        owner_flood = folia / FLOOD
        if not flood15.exists() and owner_flood.is_file():
            r21_stage = runpy.run_path(str(ROOT / "scripts/apply-never-overworld-field-r21.py"))
            reweather_method = r21_stage["REWEATHER_METHOD"]
            text = owner_flood.read_text(encoding="utf-8")
            if reweather_method in text:
                owner_flood.write_text(text.replace(reweather_method, "", 1), encoding="utf-8")
        subprocess.run(r20, cwd=ROOT, check=True)

    subprocess.run(
        [sys.executable, str(ROOT / "scripts/apply-never-overworld-field-r21.py"), str(folia)],
        cwd=ROOT, check=True
    )
    verify(folia)
    print(f"[NeverOverworld R21] {PROFILE} installed")

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia", type=Path)
    p.add_argument("--check-only", action="store_true")
    a = p.parse_args()
    folia = a.folia.resolve()
    if a.check_only:
        verify(folia)
    else:
        apply(folia)

if __name__ == "__main__":
    main()
