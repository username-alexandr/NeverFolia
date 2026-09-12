#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

NAME = "MineshaftStructure.java"
ANCHOR = "int seaLevel = chunkGenerator.getSeaLevel();"
MARKER = "// NeverFolia: VANILLA_FLOODED mineshafts are deep-only."
R9_VILLAGE_LOCATE = Path(__file__).with_name("harden-never-overworld-village-locate-r9.py")
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
    if not R9_VILLAGE_LOCATE.is_file():
        fail(f"R9 village locate transformer missing: {R9_VILLAGE_LOCATE}")
    subprocess.run([sys.executable, str(R9_VILLAGE_LOCATE), "--self-test"], check=True)
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
    folia = args.folia.resolve()
    path = find_source(folia)
    path.write_text(patch_source(path.read_text(encoding="utf-8")), encoding="utf-8")
    print("[NeverFolia][mineshaft depth] deep-only mineshaft placement applied")
    print("  range: Y=-448..-112")
    print(f"  source: {path}")

    # R9 must run after apply-never-overworld-village-layout-safety.py, because
    # R8 layout safety rewrites passesNeverOverworldPolicy() back to the expensive
    # Structure.generate()/bbox preview path. This script is the next production
    # patch-chain stage, so apply the bounded locate policy here deterministically.
    subprocess.run([sys.executable, str(R9_VILLAGE_LOCATE), str(folia)], check=True)


if __name__ == "__main__":
    main()
