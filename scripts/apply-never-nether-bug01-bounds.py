#!/usr/bin/env python3
"""BUG01: reject impossible decoration coordinates before section lookup.

Apply after the exact R14 chain. Data/height/storage profiles do not change.
No world edits, old-world migration, exception suppression or chunk fallback.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path

JAVA = Path("folia-server/src/minecraft/java")
CONTRACTS = {'net/minecraft/world/level/levelgen/placement/NeverNetherSubstrateR10.java': {'sha256': '8fe47a3c342a9fa77a17713271df03573e6160c49809ea97df488156e8737026', 'replacements': [{'old': '    public static boolean proposeSection(LevelChunkSection section, BlockPos p, BlockState proposed) {\n        return propose(null, section, p, proposed);', 'new': '    /** Proposals cannot replace the roof or occupy technical padding. Check\n     * before any chunk/section access: ensureCanWrite is not a vertical guard. */\n    public static boolean isProposalHeight(int y) {\n        return y >= NeverNetherHeightR14.MIN_Y && y < NeverNetherHeightR14.ROOF_Y;\n    }\n    public static boolean proposeSection(LevelChunkSection section, BlockPos p, BlockState proposed) {\n        if (!isProposalHeight(p.getY())) return false;\n        return propose(null, section, p, proposed);', 'count': 1}, {'old': '        if (!level.ensureCanWrite(p)) return false;', 'new': '        if (!isProposalHeight(p.getY()) || !level.ensureCanWrite(p)) return false;', 'count': 1}, {'old': '        return chunk.getSection(chunk.getSectionIndex(p.getY()));', 'new': '        int sectionIndex = chunk.getSectionIndex(p.getY());\n        if (sectionIndex < 0 || sectionIndex >= chunk.getSections().length)\n            throw new IllegalStateException("NN-BUG01 substrate coordinate outside actual section array: " + p);\n        return chunk.getSection(sectionIndex);', 'count': 1}]}, 'net/minecraft/world/level/levelgen/placement/NeverNetherFloraCandidateR8.java': {'sha256': 'c8946951df26920c1966d0f17f098688945c5e980b38ea6900f9492827076589', 'replacements': [{'old': '                if(!actual.ensureCanWrite(pos))return false;', 'new': '                if(!NeverNetherSubstrateR10.isProposalHeight(pos.getY()) || !actual.ensureCanWrite(pos))return false;', 'count': 1}]}, 'net/minecraft/world/level/levelgen/placement/NeverNetherNaturalPolicyR13.java': {'sha256': '08f4ccc278df9759f3b15d5934804087ee2544bc92de407eaec8617f90405994', 'replacements': [{'old': '        if (!allowsPlantAt(NeverNetherSubstrateR10.original(actual, pos))) return false;', 'new': '        if (!NeverNetherSubstrateR10.isProposalHeight(pos.getY())) return false;\n        if (!allowsPlantAt(NeverNetherSubstrateR10.original(actual, pos))) return false;', 'count': 1}]}}


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def transform(name: str, text: str) -> str:
    rule = CONTRACTS[name]
    if sha(text) == rule["sha256"]:
        for item in rule["replacements"]:
            if text.count(item["old"]) != item["count"] or item["new"] in text:
                raise ValueError("Unexpected BUG01 hook count: " + name)
            text = text.replace(item["old"], item["new"])
        return text
    original = text
    for item in reversed(rule["replacements"]):
        if original.count(item["new"]) != item["count"]:
            raise ValueError("BUG01 source identity mismatch: " + name)
        original = original.replace(item["new"], item["old"])
    if sha(original) != rule["sha256"]:
        raise ValueError("BUG01 patched source does not invert to inspected source: " + name)
    return text


def prepare(root: Path) -> dict[Path, str]:
    return {root / JAVA / name: transform(name, (root / JAVA / name).read_text(encoding="utf-8"))
            for name in CONTRACTS}


def apply(root: Path) -> None:
    staged = prepare(root)
    for path, text in staged.items():
        path.write_text(text, encoding="utf-8")
    print("BUG01 bounds guards installed in three sources; no datapack or metadata profile changed")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("folia", type=Path)
    args = p.parse_args()
    apply(args.folia)

if __name__ == "__main__":
    main()
