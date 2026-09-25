#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

NAME = "MineshaftStructure.java"
ANCHOR = "int seaLevel = chunkGenerator.getSeaLevel();"
MARKER = "// NeverFolia: VANILLA_FLOODED mineshafts are deep-only."
INJECTION = '''int seaLevel = chunkGenerator.getSeaLevel();
        // NeverFolia: VANILLA_FLOODED mineshafts are deep-only.
        // Keep the complete bounding box inside Y=-448..-112 so rails never
        // generate in the flooded surface domain. This is deterministic because
        // it consumes only the structure's existing seeded WorldgenRandom.
        if (context.heightAccessor().getMinY() == -512 && context.heightAccessor().getHeight() == 1024) {
            final net.minecraft.world.level.levelgen.structure.BoundingBox neverFoliaBox = builder.getBoundingBox();
            final int neverFoliaMinY = -448;
            final int neverFoliaMaxY = -112;
            final int neverFoliaHighestMin = Math.max(neverFoliaMinY, neverFoliaMaxY - neverFoliaBox.getYSpan() + 1);
            final int neverFoliaTargetMin = net.minecraft.util.Mth.randomBetweenInclusive(random, neverFoliaMinY, neverFoliaHighestMin);
            final int neverFoliaOffset = neverFoliaTargetMin - neverFoliaBox.minY();
            builder.offsetPiecesVertically(neverFoliaOffset);
            return neverFoliaOffset;
        }'''


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][mineshaft depth] {message}")


def find_source(folia: Path) -> Path:
    candidates = [p for p in (folia / "folia-server").rglob(NAME) if ".gradle" not in p.parts and "taskCache" not in p.parts]
    candidates = [p for p in candidates if "class MineshaftStructure" in p.read_text(encoding="utf-8")]
    if len(candidates) != 1:
        fail(f"expected one runtime {NAME}, got {len(candidates)}: {candidates}")
    return candidates[0]


def patch_source(source: str) -> str:
    if MARKER in source:
        fail("mineshaft depth policy already applied")
    if source.count(ANCHOR) != 1:
        fail(f"expected one sea-level anchor, got {source.count(ANCHOR)}")
    patched = source.replace(ANCHOR, INJECTION, 1)
    for marker in ("neverFoliaMinY = -448", "neverFoliaMaxY = -112", "getYSpan()", "offsetPiecesVertically"):
        if marker not in patched:
            fail(f"patched source missing {marker}")
    return patched


def self_test() -> None:
    fixture = '''class MineshaftStructure {
    private int generatePiecesAndAdjust(StructurePiecesBuilder builder, Structure.GenerationContext context) {
        ChunkPos chunkPos = context.chunkPos();
        WorldgenRandom random = context.random();
        ChunkGenerator chunkGenerator = context.chunkGenerator();
        int seaLevel = chunkGenerator.getSeaLevel();
        if (this.type == Type.MESA) { return 1; }
        return builder.moveBelowSeaLevel(seaLevel, chunkGenerator.getMinY(), random, 10);
    }
}
'''
    patched = patch_source(fixture)
    if patched.count(MARKER) != 1:
        fail("SELF-TEST marker count drifted")
    print("[NeverFolia][mineshaft depth] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("folia", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.folia is None:
        parser.error("folia worktree is required unless --self-test is used")
    self_test()
    path = find_source(args.folia.resolve())
    path.write_text(patch_source(path.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][mineshaft depth] deep-only mineshaft placement applied")
    print(f"  range: Y=-448..-112")
    print(f"  source: {path}")


if __name__ == "__main__":
    main()
