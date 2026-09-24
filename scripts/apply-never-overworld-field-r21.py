#!/usr/bin/env python3
"""FIELD-R21: Moonrise runtime cache-aware flood seam reconciliation.

Runs after FIELD-R20. Folia 26.2 bypasses vanilla ChunkStatusTasks.light() and
executes LIGHT through Moonrise ChunkLightTask. R21 therefore carries Moonrise's
already-built neighbour StaticCache2D into ChunkLightTask and reconciles the
owner chunk immediately after the existing owner flood, before Starlight reads
section emptiness. No synchronous chunk loads or WorldGenLevel neighbour reads.
"""
from __future__ import annotations

import argparse
from pathlib import Path

JAVA = Path("folia-server/src/minecraft/java")
TASKS = JAVA / "net/minecraft/world/level/chunk/status/ChunkStatusTasks.java"
FLOOD15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"
MOONRISE = JAVA / "ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask.java"
SCHEDULER = JAVA / "ca/spottedleaf/moonrise/patches/chunk_system/scheduling/ChunkTaskScheduler.java"

OWNER_CALL = "net.minecraft.world.level.chunk.NeverOverworldFlood.apply(task.world, task.fromChunk);"
RECONCILE_CALL = (
    "net.minecraft.world.level.chunk.NeverOverworldFloodConnectivityR15."
    "reconcileSeams(task.neverOverworldNeighbours, task.fromChunk);"
)
CACHE_FIELD = "    private final StaticCache2D<GenerationChunkHolder> neverOverworldNeighbours;"

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[FIELD-R21] " + message)

def patch_moonrise(text: str) -> str:
    if "import net.minecraft.server.level.GenerationChunkHolder;" not in text:
        anchor = "import net.minecraft.server.level.ServerLevel;\n"
        require(anchor in text, "Moonrise ServerLevel import anchor missing")
        text = text.replace(anchor, "import net.minecraft.server.level.GenerationChunkHolder;\n" + anchor, 1)
    if "import net.minecraft.util.StaticCache2D;" not in text:
        anchor = "import net.minecraft.world.level.ChunkPos;\n"
        require(anchor in text, "Moonrise ChunkPos import anchor missing")
        text = text.replace(anchor, "import net.minecraft.util.StaticCache2D;\n" + anchor, 1)

    if CACHE_FIELD not in text:
        anchor = "    private final ChunkAccess fromChunk;\n"
        require(anchor in text, "Moonrise fromChunk field anchor missing")
        text = text.replace(anchor, anchor + "\n" + CACHE_FIELD + "\n", 1)

    if "final StaticCache2D<GenerationChunkHolder> neighbours" not in text:
        old = "                          final ChunkAccess chunk, final Priority priority) {"
        new = (
            "                          final ChunkAccess chunk, "
            "final StaticCache2D<GenerationChunkHolder> neighbours, final Priority priority) {"
        )
        require(old in text, "Moonrise constructor signature anchor missing")
        text = text.replace(old, new, 1)

    if "this.neverOverworldNeighbours = neighbours;" not in text:
        anchor = "        this.fromChunk = chunk;\n"
        require(anchor in text, "Moonrise fromChunk assignment anchor missing")
        text = text.replace(anchor, anchor + "        this.neverOverworldNeighbours = neighbours;\n", 1)

    if RECONCILE_CALL not in text:
        require(text.count(OWNER_CALL) == 1, "Moonrise owner flood call missing/duplicated")
        text = text.replace(OWNER_CALL, OWNER_CALL + "\n                " + RECONCILE_CALL, 1)
    return text

def patch_scheduler(text: str) -> str:
    old = "return new ChunkLightTask(this, this.world, chunkX, chunkZ, chunk, initialPriority);"
    new = "return new ChunkLightTask(this, this.world, chunkX, chunkZ, chunk, neighbours, initialPriority);"
    if new in text:
        return text
    require(text.count(old) == 1, "Moonrise scheduler LIGHT constructor anchor missing")
    return text.replace(old, new, 1)

def verify(folia: Path) -> None:
    tasks = (folia / TASKS).read_text(encoding="utf-8")
    flood = (folia / FLOOD15).read_text(encoding="utf-8")
    moonrise = (folia / MOONRISE).read_text(encoding="utf-8")
    scheduler = (folia / SCHEDULER).read_text(encoding="utf-8")

    # Vanilla ChunkStatusTasks.light is bypassed by Moonrise on Folia. Keeping a
    # second owner-flood/reconcile there is misleading and can never be the
    # authoritative runtime contract.
    require("NeverOverworldFloodConnectivityR15.reconcileSeams(" not in tasks,
            "bypassed ChunkStatusTasks still contains R21 reconcile hook")
    require("NeverOverworldFlood.apply(" not in tasks,
            "bypassed ChunkStatusTasks still contains duplicate owner flood")

    require(moonrise.count(OWNER_CALL) == 1,
            "Moonrise LIGHT must contain exactly one owner flood")
    require(moonrise.count(RECONCILE_CALL) == 1,
            "Moonrise LIGHT must contain exactly one seam reconciliation")
    require(moonrise.find(OWNER_CALL) < moonrise.find(RECONCILE_CALL)
            < moonrise.find("StarLightEngine.getEmptySectionsForChunk"),
            "Moonrise runtime order must be owner flood -> seam reconcile -> Starlight")
    require(CACHE_FIELD in moonrise,
            "Moonrise LIGHT neighbour cache field missing")
    require("this.neverOverworldNeighbours = neighbours;" in moonrise,
            "Moonrise LIGHT neighbour cache assignment missing")
    require("new ChunkLightTask(this, this.world, chunkX, chunkZ, chunk, neighbours, initialPriority)" in scheduler,
            "Moonrise scheduler does not pass the existing neighbour cache to LIGHT")

    for marker in (
        "StaticCache2D<GenerationChunkHolder>",
        "getChunkIfPresent(ChunkStatus.FEATURES)",
        "oceanConnectedFloodable",
        "externalSeeds",
        "allowSeams",
    ):
        require(marker in flood, "R21 flood helper marker missing: " + marker)
    require("if (!traversable(chunk, pos)) return tailIn;" in flood,
            "R21 neighbour connectivity must traverse floodable volume")
    require("scan(chunk,visited,queue,x,y,z,minY,maxY,externalSeeds,allowSeams)" in flood,
            "R21 component scan must receive external seam seeds")
    require("boolean[] externalSeeds,boolean allowSeams" in flood,
            "R21 component scan seam parameters missing")
    require("level.getBlockState(" not in flood and "getChunk(" not in flood,
            "R21 must not synchronously load/read neighbours through level")

    print("[FIELD-R21] Moonrise runtime cache-aware seam reconciliation invariants OK")

def apply(folia: Path) -> None:
    moonrise = folia / MOONRISE
    scheduler = folia / SCHEDULER
    tasks = folia / TASKS
    require(moonrise.is_file(), "Moonrise ChunkLightTask missing")
    require(scheduler.is_file(), "Moonrise ChunkTaskScheduler missing")
    require(tasks.is_file(), "ChunkStatusTasks missing")

    # Remove the dead R21 canonical hook if an earlier R21 attempt materialized it.
    tasks_text = tasks.read_text(encoding="utf-8")
    dead_markers = (
        "NeverOverworldFlood.apply(",
        "NeverOverworldFloodConnectivityR15.reconcileSeams(",
        "// NeverFolia: LIGHT has a radius-1 INITIALIZE_LIGHT dependency. Every",
        "// neighboring chunk that can write FEATURES into this chunk has therefore",
        "// finished decoration before the chunk-owned flood mutates final blocks.",
    )
    tasks_text = "\n".join(
        line for line in tasks_text.split("\n")
        if not any(marker in line for marker in dead_markers)
    )
    tasks.write_text(tasks_text, encoding="utf-8")

    moonrise.write_text(patch_moonrise(moonrise.read_text(encoding="utf-8")), encoding="utf-8")
    scheduler.write_text(patch_scheduler(scheduler.read_text(encoding="utf-8")), encoding="utf-8")
    verify(folia)
    print("[FIELD-R21] installed in actual Moonrise LIGHT runtime path")

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
