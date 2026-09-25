#!/usr/bin/env python3
"""FIELD-R21: Moonrise runtime cache-aware flood seam reconciliation.

Runs after FIELD-R20. Folia 26.2 bypasses vanilla ChunkStatusTasks.light() and
executes LIGHT through Moonrise ChunkLightTask. R21 therefore carries Moonrise's neighbour StaticCache2D into ChunkLightTask.
NeverFolia requests a stable radius-3 FEATURES dependency for LIGHT and then
reconciles only the owner chunk after the existing owner flood. Because reconciliation
can create new water after the earlier FEATURES ecology passes, R13/R15 ecology
cleanup runs once more on the same owner chunk before Starlight reads section
emptiness. No synchronous chunk loads or WorldGenLevel neighbour reads.
"""
from __future__ import annotations

import argparse
from pathlib import Path

JAVA = Path("folia-server/src/minecraft/java")
TASKS = JAVA / "net/minecraft/world/level/chunk/status/ChunkStatusTasks.java"
FLOOD = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFlood.java"
FLOOD15 = JAVA / "net/minecraft/world/level/chunk/NeverOverworldFloodConnectivityR15.java"
MOONRISE = JAVA / "ca/spottedleaf/moonrise/patches/chunk_system/scheduling/task/ChunkLightTask.java"
SCHEDULER = JAVA / "ca/spottedleaf/moonrise/patches/chunk_system/scheduling/ChunkTaskScheduler.java"

OWNER_CALL = "net.minecraft.world.level.chunk.NeverOverworldFlood.apply(task.world, task.fromChunk);"
RECONCILE_CALL = (
    "net.minecraft.world.level.chunk.NeverOverworldFloodConnectivityR15."
    "reconcileSeams(task.world, task.neverOverworldNeighbours, task.fromChunk);"
)
REWEATHER_CALL = "net.minecraft.world.level.chunk.NeverOverworldFlood.reweatherSubmergedSurface(task.world, task.fromChunk);"
ECOLOGY13_CALL = "net.minecraft.world.level.chunk.NeverOverworldEcologyR13.cleanup(task.world, task.fromChunk);"
ECOLOGY15_CALL = "net.minecraft.world.level.chunk.NeverOverworldEcologyR15.cleanup(task.world, task.fromChunk);"
CACHE_FIELD = "    private final StaticCache2D<GenerationChunkHolder> neverOverworldNeighbours;"

LIGHT_RADIUS_OLD = """        final int neighbourReadRadius = Math.max(
                0,
                chunkStep.getAccumulatedRadiusOf(ChunkStatus.EMPTY)
        );
"""
LIGHT_RADIUS_NEW = """        final int vanillaNeighbourReadRadius = Math.max(
                0,
                chunkStep.getAccumulatedRadiusOf(ChunkStatus.EMPTY)
        );
        // NeverFolia: exact ocean connectivity needs a stable radius-2
        // FEATURES view before LIGHT; flood writes remain owner-only.
        final int neighbourReadRadius = toStatus == ChunkStatus.LIGHT
                ? Math.max(3, vanillaNeighbourReadRadius)
                : vanillaNeighbourReadRadius;
"""
LIGHT_REQUIRED_OLD = """                final ChunkStatus requiredNeighbourStatus = ((ChunkSystemChunkStep)(Object)chunkStep).moonrise$getRequiredStatusAtRadius(radius);
"""
LIGHT_REQUIRED_NEW = """                final ChunkStatus requiredNeighbourStatus =
                        toStatus == ChunkStatus.LIGHT && radius > vanillaNeighbourReadRadius
                                ? ChunkStatus.FEATURES
                                : ((ChunkSystemChunkStep)(Object)chunkStep).moonrise$getRequiredStatusAtRadius(radius);
"""

REWEATHER_METHOD_ANCHOR = "    private static void weatherSubmergedSurface(\n"
REWEATHER_METHOD = """    /**
     * R21/R22: seam reconciliation may flood a column after the owner's first
     * drowned-surface pass. Reuse the existing deterministic weathering policy
     * before Starlight observes/persists the reconciled chunk.
     */
    public static void reweatherSubmergedSurface(
        final WorldGenLevel level,
        final ChunkAccess chunk
    ) {
        if (!level.getLevel().dimension().equals(Level.OVERWORLD)
            || level.getMinY() != EXPECTED_MIN_Y
            || level.getHeight() != EXPECTED_HEIGHT) {
            return;
        }
        weatherSubmergedSurface(chunk, level.getMinY() + 1, FLOOD_LEVEL);
    }

"""

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError("[FIELD-R21] " + message)

def patch_flood(text: str) -> str:
    if "public static void reweatherSubmergedSurface(" in text:
        return text
    require(text.count(REWEATHER_METHOD_ANCHOR) == 1,
            "drowned-surface weathering method anchor missing/duplicated")
    return text.replace(REWEATHER_METHOD_ANCHOR, REWEATHER_METHOD + REWEATHER_METHOD_ANCHOR, 1)

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
    if REWEATHER_CALL not in text:
        require(text.count(RECONCILE_CALL) == 1, "Moonrise seam reconcile call missing/duplicated")
        text = text.replace(RECONCILE_CALL, RECONCILE_CALL + "\n                " + REWEATHER_CALL, 1)
    if ECOLOGY13_CALL not in text:
        require(text.count(REWEATHER_CALL) == 1, "Moonrise post-seam weathering call missing/duplicated")
        text = text.replace(REWEATHER_CALL, REWEATHER_CALL + "\n                " + ECOLOGY13_CALL, 1)
    if ECOLOGY15_CALL not in text:
        require(text.count(ECOLOGY13_CALL) == 1, "Moonrise R13 ecology call missing/duplicated")
        text = text.replace(ECOLOGY13_CALL, ECOLOGY13_CALL + "\n                " + ECOLOGY15_CALL, 1)
    return text

def patch_scheduler(text: str) -> str:
    old_ctor = "return new ChunkLightTask(this, this.world, chunkX, chunkZ, chunk, initialPriority);"
    new_ctor = "return new ChunkLightTask(this, this.world, chunkX, chunkZ, chunk, neighbours, initialPriority);"
    if new_ctor not in text:
        require(text.count(old_ctor) == 1, "Moonrise scheduler LIGHT constructor anchor missing")
        text = text.replace(old_ctor, new_ctor, 1)

    if LIGHT_RADIUS_NEW not in text:
        require(text.count(LIGHT_RADIUS_OLD) == 1,
                "Moonrise scheduler neighbourReadRadius anchor missing/drifted")
        text = text.replace(LIGHT_RADIUS_OLD, LIGHT_RADIUS_NEW, 1)

    if LIGHT_REQUIRED_NEW not in text:
        require(text.count(LIGHT_REQUIRED_OLD) == 1,
                "Moonrise scheduler required-neighbour anchor missing/drifted")
        text = text.replace(LIGHT_REQUIRED_OLD, LIGHT_REQUIRED_NEW, 1)
    return text

def verify(folia: Path) -> None:
    tasks = (folia / TASKS).read_text(encoding="utf-8")
    owner_flood = (folia / FLOOD).read_text(encoding="utf-8")
    flood = (folia / FLOOD15).read_text(encoding="utf-8")
    moonrise = (folia / MOONRISE).read_text(encoding="utf-8")
    scheduler = (folia / SCHEDULER).read_text(encoding="utf-8")

    # Vanilla ChunkStatusTasks.light is bypassed by Moonrise on Folia. Keeping a
    # second owner-flood/reconcile there is misleading and can never be the
    # authoritative runtime contract.
    require(owner_flood.count("public static void reweatherSubmergedSurface(") == 1,
            "owner flood must expose exactly one post-seam weathering entry point")
    require("weatherSubmergedSurface(chunk, level.getMinY() + 1, FLOOD_LEVEL);" in owner_flood,
            "post-seam weathering must reuse the canonical drowned-surface pass")

    require("NeverOverworldFloodConnectivityR15.reconcileSeams(" not in tasks,
            "bypassed ChunkStatusTasks still contains R21 reconcile hook")
    require("NeverOverworldFlood.apply(" not in tasks,
            "bypassed ChunkStatusTasks still contains duplicate owner flood")

    require(moonrise.count(OWNER_CALL) == 1,
            "Moonrise LIGHT must contain exactly one owner flood")
    require(moonrise.count(RECONCILE_CALL) == 1,
            "Moonrise LIGHT must contain exactly one seam reconciliation")
    require(moonrise.count(REWEATHER_CALL) == 1,
            "Moonrise LIGHT must run post-seam drowned-surface weathering exactly once")
    require(moonrise.count(ECOLOGY13_CALL) == 1 and moonrise.count(ECOLOGY15_CALL) == 1,
            "Moonrise LIGHT must run post-seam ecology cleanup exactly once")
    require(moonrise.find(OWNER_CALL) < moonrise.find(RECONCILE_CALL)
            < moonrise.find(REWEATHER_CALL)
            < moonrise.find(ECOLOGY13_CALL) < moonrise.find(ECOLOGY15_CALL)
            < moonrise.find("StarLightEngine.getEmptySectionsForChunk"),
            "Moonrise runtime order must be owner flood -> seam reconcile -> weathering -> ecology -> Starlight")
    require(CACHE_FIELD in moonrise,
            "Moonrise LIGHT neighbour cache field missing")
    require("this.neverOverworldNeighbours = neighbours;" in moonrise,
            "Moonrise LIGHT neighbour cache assignment missing")
    require("new ChunkLightTask(this, this.world, chunkX, chunkZ, chunk, neighbours, initialPriority)" in scheduler,
            "Moonrise scheduler does not pass the existing neighbour cache to LIGHT")
    require(LIGHT_RADIUS_NEW in scheduler,
            "NeverFolia LIGHT must request a real radius-3 scheduler cache")
    require(LIGHT_REQUIRED_NEW in scheduler,
            "NeverFolia LIGHT outer cache ring must be generated through FEATURES")

    for marker in (
        "StaticCache2D<GenerationChunkHolder>",
        "reconcileSeams(final WorldGenLevel level",
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
    owner_flood = folia / FLOOD
    moonrise = folia / MOONRISE
    scheduler = folia / SCHEDULER
    tasks = folia / TASKS
    require(owner_flood.is_file(), "NeverOverworldFlood missing")
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

    owner_flood.write_text(patch_flood(owner_flood.read_text(encoding="utf-8")), encoding="utf-8")
    moonrise.write_text(patch_moonrise(moonrise.read_text(encoding="utf-8")), encoding="utf-8")
    scheduler.write_text(patch_scheduler(scheduler.read_text(encoding="utf-8")), encoding="utf-8")
    verify(folia)
    print("[FIELD-R21] installed in Moonrise LIGHT with radius-3 FEATURES dependency")

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
