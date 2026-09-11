#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

HELPER_REL = Path("folia-server/src/minecraft/java/net/minecraft/world/level/chunk/NeverOverworldFlood.java")
CALL_ANCHOR = "        floodSurfaceConnectedVolume(chunk, minY, FLOOD_LEVEL, water);\n"
INSERT_ANCHOR = "    private static boolean isFloodable(final BlockState state) {\n"
CALL = "        floodLargeBoundaryConnectedCaverns(chunk, minY, FLOOD_LEVEL, water);\n"

METHODS = r'''    /**
     * R8 fallback for huge cave systems that cross chunk borders.
     *
     * The primary flood remains strictly surface-connected inside the owning
     * chunk. A giant carved cavern can however enter through a neighbouring
     * chunk and therefore have no local Y=128 seed. We treat only very large
     * residual components touching a horizontal chunk face as externally open.
     * Small sealed caves stay dry.
     *
     * No neighbouring chunk is read or written. This keeps Folia generation
     * chunk-order independent. Valid structure-start bounding boxes are treated
     * as solid barriers so dry generated rooms are not used as flood conduits.
     */
    private static void floodLargeBoundaryConnectedCaverns(
        final ChunkAccess chunk,
        final int minY,
        final int maxY,
        final BlockState water
    ) {
        final int scanMinY = Math.max(minY, -384);
        final int scanMaxY = Math.min(maxY, 96);
        if (scanMinY > scanMaxY) {
            return;
        }

        final int layerCount = scanMaxY - scanMinY + 1;
        final int capacity = layerCount * 256;
        final boolean[] visited = new boolean[capacity];
        final int[] queue = new int[capacity];
        final java.util.List<net.minecraft.world.level.levelgen.structure.BoundingBox> protectedBoxes = protectionBoxes(chunk);
        final ChunkPos chunkPos = chunk.getPos();
        final int minX = chunkPos.getMinBlockX();
        final int minZ = chunkPos.getMinBlockZ();

        for (int y = scanMinY; y <= scanMaxY; ++y) {
            for (int edge = 0; edge < 16; ++edge) {
                scanBoundaryComponent(chunk, water, protectedBoxes, visited, queue, 0, y, edge, minX, minZ, scanMinY, scanMaxY);
                scanBoundaryComponent(chunk, water, protectedBoxes, visited, queue, 15, y, edge, minX, minZ, scanMinY, scanMaxY);
                scanBoundaryComponent(chunk, water, protectedBoxes, visited, queue, edge, y, 0, minX, minZ, scanMinY, scanMaxY);
                scanBoundaryComponent(chunk, water, protectedBoxes, visited, queue, edge, y, 15, minX, minZ, scanMinY, scanMaxY);
            }
        }
    }

    private static void scanBoundaryComponent(
        final ChunkAccess chunk,
        final BlockState water,
        final java.util.List<net.minecraft.world.level.levelgen.structure.BoundingBox> protectedBoxes,
        final boolean[] visited,
        final int[] queue,
        final int seedLocalX,
        final int seedY,
        final int seedLocalZ,
        final int minX,
        final int minZ,
        final int minY,
        final int maxY
    ) {
        final int seed = encode(seedLocalX, seedY, seedLocalZ, minY);
        if (visited[seed]) {
            return;
        }
        final BlockPos.MutableBlockPos pos = new BlockPos.MutableBlockPos();
        final int seedX = minX + seedLocalX;
        final int seedZ = minZ + seedLocalZ;
        pos.set(seedX, seedY, seedZ);
        if (!isFloodable(chunk.getBlockState(pos)) || isProtected(protectedBoxes, seedX, seedY, seedZ)) {
            visited[seed] = true;
            return;
        }

        int head = 0;
        int tail = 0;
        int boundaryCells = 0;
        int componentMinY = seedY;
        int componentMaxY = seedY;
        visited[seed] = true;
        queue[tail++] = seed;

        while (head < tail) {
            final int encoded = queue[head++];
            final int localX = encoded & 15;
            final int localZ = (encoded >>> 4) & 15;
            final int y = minY + (encoded >>> 8);
            componentMinY = Math.min(componentMinY, y);
            componentMaxY = Math.max(componentMaxY, y);
            if (localX == 0 || localX == 15 || localZ == 0 || localZ == 15) {
                ++boundaryCells;
            }

            tail = enqueueR8(chunk, protectedBoxes, queue, visited, tail, localX - 1, y, localZ, minX, minZ, minY, maxY);
            tail = enqueueR8(chunk, protectedBoxes, queue, visited, tail, localX + 1, y, localZ, minX, minZ, minY, maxY);
            tail = enqueueR8(chunk, protectedBoxes, queue, visited, tail, localX, y, localZ - 1, minX, minZ, minY, maxY);
            tail = enqueueR8(chunk, protectedBoxes, queue, visited, tail, localX, y, localZ + 1, minX, minZ, minY, maxY);
            tail = enqueueR8(chunk, protectedBoxes, queue, visited, tail, localX, y - 1, localZ, minX, minZ, minY, maxY);
            tail = enqueueR8(chunk, protectedBoxes, queue, visited, tail, localX, y + 1, localZ, minX, minZ, minY, maxY);
        }

        final int verticalSpan = componentMaxY - componentMinY + 1;
        if (tail < 768 || boundaryCells < 48 || verticalSpan < 24) {
            return;
        }

        for (int index = 0; index < tail; ++index) {
            final int encoded = queue[index];
            final int localX = encoded & 15;
            final int localZ = (encoded >>> 4) & 15;
            final int y = minY + (encoded >>> 8);
            final int x = minX + localX;
            final int z = minZ + localZ;
            if (isProtected(protectedBoxes, x, y, z)) {
                continue;
            }
            pos.set(x, y, z);
            if (isFloodable(chunk.getBlockState(pos))) {
                chunk.setBlockState(pos, water, 0);
            }
        }
    }

    private static int enqueueR8(
        final ChunkAccess chunk,
        final java.util.List<net.minecraft.world.level.levelgen.structure.BoundingBox> protectedBoxes,
        final int[] queue,
        final boolean[] visited,
        int tail,
        final int localX,
        final int y,
        final int localZ,
        final int minX,
        final int minZ,
        final int minY,
        final int maxY
    ) {
        if (localX < 0 || localX > 15 || localZ < 0 || localZ > 15 || y < minY || y > maxY) {
            return tail;
        }
        final int encoded = encode(localX, y, localZ, minY);
        if (visited[encoded]) {
            return tail;
        }
        final int x = minX + localX;
        final int z = minZ + localZ;
        final BlockPos pos = new BlockPos(x, y, z);
        if (!isFloodable(chunk.getBlockState(pos)) || isProtected(protectedBoxes, x, y, z)) {
            visited[encoded] = true;
            return tail;
        }
        visited[encoded] = true;
        queue[tail++] = encoded;
        return tail;
    }

    private static java.util.List<net.minecraft.world.level.levelgen.structure.BoundingBox> protectionBoxes(final ChunkAccess chunk) {
        final java.util.ArrayList<net.minecraft.world.level.levelgen.structure.BoundingBox> result = new java.util.ArrayList<>();
        for (final net.minecraft.world.level.levelgen.structure.StructureStart start : chunk.getAllStarts().values()) {
            if (start != null && start.isValid()) {
                result.add(start.getBoundingBox());
            }
        }
        return result;
    }

    private static boolean isProtected(
        final java.util.List<net.minecraft.world.level.levelgen.structure.BoundingBox> boxes,
        final int x,
        final int y,
        final int z
    ) {
        for (final net.minecraft.world.level.levelgen.structure.BoundingBox box : boxes) {
            if (x >= box.minX() - 2 && x <= box.maxX() + 2
                && y >= box.minY() - 2 && y <= box.maxY() + 2
                && z >= box.minZ() - 2 && z <= box.maxZ() + 2) {
                return true;
            }
        }
        return false;
    }

'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld flood connectivity R8] {message}")


def patch(source: str) -> str:
    if "floodLargeBoundaryConnectedCaverns" in source:
        fail("R8 flood connectivity already applied")
    if source.count(CALL_ANCHOR) != 1:
        fail(f"expected one final surface-connected flood call, got {source.count(CALL_ANCHOR)}")
    if source.count(INSERT_ANCHOR) != 1:
        fail("final isFloodable insertion anchor missing")
    if "floodSurfaceConnectedVolume" not in source or "enqueueFloodable" not in source:
        fail("floodable-volume semantics must be applied before R8")
    out = source.replace(CALL_ANCHOR, CALL_ANCHOR + CALL, 1)
    out = out.replace(INSERT_ANCHOR, METHODS + INSERT_ANCHOR, 1)
    for marker in (
        "tail < 768",
        "boundaryCells < 48",
        "verticalSpan < 24",
        "chunk.getAllStarts().values()",
        "box.minX() - 2",
        "scanMinY = Math.max(minY, -384)",
    ):
        if marker not in out:
            fail(f"patched helper missing {marker!r}")
    return out


def self_test() -> None:
    fixture = '''class NeverOverworldFlood {
    void apply() {
        floodSurfaceConnectedVolume(chunk, minY, FLOOD_LEVEL, water);
    }
    private static void floodSurfaceConnectedVolume(Object chunk, int minY, int maxY, Object water) {}
    private static int enqueueFloodable() { return 0; }
    private static boolean isFloodable(final BlockState state) {
        return state.isAir() || (state.getFluidState().isEmpty() && state.canBeReplaced());
    }
    private static int encode(final int localX, final int y, final int localZ, final int minY) { return 0; }
}
'''
    out = patch(fixture)
    if out.count("floodLargeBoundaryConnectedCaverns(chunk, minY, FLOOD_LEVEL, water);") != 1:
        fail("SELF-TEST: fallback call missing")
    if "chunk.getAllStarts().values()" not in out:
        fail("SELF-TEST: structure protection missing")
    if "localX < 0 || localX > 15" not in out:
        fail("SELF-TEST: chunk ownership guard missing")
    print("[NeverFolia][NeverOverworld flood connectivity R8] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree path required")
    self_test()
    helper = args.folia.resolve() / HELPER_REL
    if not helper.is_file():
        fail(f"NeverOverworldFlood helper missing: {helper}")
    helper.write_text(patch(helper.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][NeverOverworld flood connectivity R8] large cross-chunk cavern fallback installed")
    print("  scan range: Y=-384..96")
    print("  thresholds: >=768 blocks, >=48 boundary cells, >=24 vertical span")
    print("  neighbour chunk reads/writes: none")
    print("  structure starts: bbox+2 protected")


if __name__ == "__main__":
    main()
