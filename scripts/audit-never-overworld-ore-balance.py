#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_AUDITOR = ROOT / "scripts/audit-never-overworld-native-geology.py"

spec = importlib.util.spec_from_file_location("native_audit", BASE_AUDITOR)
if spec is None or spec.loader is None:
    raise SystemExit(f"cannot import native geology auditor: {BASE_AUDITOR}")
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)

DEEP_MIN_SECTION = -32          # Y=-512
DEEP_MAX_SECTION = -7           # Y=-97
VANILLA_MIN_SECTION = -4        # Y=-64
VANILLA_MAX_SECTION = 19        # Y=319


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld ore balance audit] {message}")


def sample_key(coord: tuple[int, int]) -> bytes:
    cx, cz = coord
    return hashlib.sha256(f"NR-ORE-BALANCE:{cx},{cz}".encode("ascii")).digest()


def deterministic_sample(region: Path, max_chunks: int) -> list[tuple[int, int]]:
    coords = list(dict.fromkeys(A.generated_chunks(region)))
    if not coords:
        fail("no generated chunks found")
    coords.sort(key=sample_key)
    return coords[:max_chunks]


def per_chunk(counts: Counter[str], chunks: int) -> dict[str, float]:
    return {kind: round(counts.get(kind, 0) / chunks, 6) for kind in A.ORE_KINDS}


def ratio(deep: Counter[str], vanilla: Counter[str]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for kind in A.ORE_KINDS:
        v = vanilla.get(kind, 0)
        result[kind] = None if v <= 0 else round(deep.get(kind, 0) / v, 6)
    return result


def audit(world: Path, max_chunks: int) -> dict:
    region = A.NR.find_region_dir(world)
    sample = deterministic_sample(region, max_chunks)
    deep: Counter[str] = Counter()
    deep_blocks: Counter[str] = Counter()
    vanilla: Counter[str] = Counter()
    vanilla_blocks: Counter[str] = Counter()
    chunks_scanned = 0
    deep_sections = 0
    vanilla_sections = 0
    chunks_with_deep = Counter()
    chunks_with_vanilla = Counter()

    for cx, cz in sample:
        try:
            root = A.BASE.read_chunk_nbt(region, cx, cz)
        except Exception:
            continue
        chunks_scanned += 1
        deep_before = deep.copy()
        vanilla_before = vanilla.copy()
        for section in A.BASE.section_list(root):
            sy = section.get("Y")
            if not isinstance(sy, int):
                continue
            if DEEP_MIN_SECTION <= sy <= DEEP_MAX_SECTION:
                deep_sections += 1
                A.count_section(section, deep, deep_blocks)
            elif VANILLA_MIN_SECTION <= sy <= VANILLA_MAX_SECTION:
                vanilla_sections += 1
                A.count_section(section, vanilla, vanilla_blocks)
        for kind in A.ORE_KINDS:
            if deep.get(kind, 0) > deep_before.get(kind, 0):
                chunks_with_deep[kind] += 1
            if vanilla.get(kind, 0) > vanilla_before.get(kind, 0):
                chunks_with_vanilla[kind] += 1

    if chunks_scanned == 0:
        fail("sample contained no readable chunks")
    if vanilla_sections == 0 or deep_sections == 0:
        fail(f"expected both vanilla and deep sections, got vanilla={vanilla_sections} deep={deep_sections}")

    result = {
        "schema": 1,
        "sample_method": "sha256-spatial-mix-v1",
        "chunks_requested": max_chunks,
        "chunks_scanned": chunks_scanned,
        "deep_y": [-512, -97],
        "vanilla_reference_y": [-64, 319],
        "deep_sections_scanned": deep_sections,
        "vanilla_sections_scanned": vanilla_sections,
        "deep_ore_blocks": {kind: deep.get(kind, 0) for kind in A.ORE_KINDS},
        "vanilla_reference_ore_blocks": {kind: vanilla.get(kind, 0) for kind in A.ORE_KINDS},
        "deep_ore_blocks_per_chunk": per_chunk(deep, chunks_scanned),
        "vanilla_reference_ore_blocks_per_chunk": per_chunk(vanilla, chunks_scanned),
        "deep_to_vanilla_ratio": ratio(deep, vanilla),
        "chunks_with_deep_ore": {kind: chunks_with_deep.get(kind, 0) for kind in A.ORE_KINDS},
        "chunks_with_vanilla_reference_ore": {kind: chunks_with_vanilla.get(kind, 0) for kind in A.ORE_KINDS},
        "deep_ore_block_variants": {block: deep_blocks.get(block, 0) for block in sorted(A.ORE_NAMES)},
        "vanilla_reference_ore_block_variants": {block: vanilla_blocks.get(block, 0) for block in sorted(A.ORE_NAMES)},
    }
    return result


def self_test() -> None:
    coords = [(0, 0), (1, 1), (-1, 7), (55, -9)]
    first = sorted(coords, key=sample_key)
    second = sorted(reversed(coords), key=sample_key)
    if first != second:
        fail("SELF-TEST: deterministic sample ordering is unstable")
    d = Counter({"iron": 20, "diamond": 5})
    v = Counter({"iron": 10, "diamond": 0})
    r = ratio(d, v)
    if r["iron"] != 2.0 or r["diamond"] is not None:
        fail("SELF-TEST: ratio calculation failed")
    print("[NeverFolia][NeverOverworld ore balance audit] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare NR deep native ore density with preserved vanilla 26.2 ore density")
    parser.add_argument("--world", type=Path)
    parser.add_argument("--max-chunks", type=int, default=1024)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.world is None or args.output is None:
        parser.error("--world and --output are required")
    if args.max_chunks <= 0:
        parser.error("--max-chunks must be positive")

    result = audit(args.world.resolve(), args.max_chunks)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
