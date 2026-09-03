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

MIN_SECTION = -4   # Y=-64
MAX_SECTION = 19   # Y=319
FULL = {"full", "minecraft:full"}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][Vanilla ore reference audit] {message}")


def key(coord: tuple[int, int]) -> bytes:
    return hashlib.sha256(f"VANILLA-ORE-REF:{coord[0]},{coord[1]}".encode("ascii")).digest()


def status(root: dict) -> str:
    value = root.get("Status", root.get("status", ""))
    return value if isinstance(value, str) else ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit true vanilla 26.2 ore density in FULL chunks")
    parser.add_argument("--world", required=True, type=Path)
    parser.add_argument("--max-chunks", type=int, default=1024)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    region = A.NR.find_region_dir(args.world.resolve())
    coords = list(dict.fromkeys(A.generated_chunks(region)))
    coords.sort(key=key)
    ores: Counter[str] = Counter()
    blocks: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    chunks_with = Counter()
    full_chunks = 0
    sections = 0

    for cx, cz in coords:
        if full_chunks >= args.max_chunks:
            break
        try:
            root = A.BASE.read_chunk_nbt(region, cx, cz)
        except Exception:
            continue
        s = status(root)
        status_counts[s or "<missing>"] += 1
        if s not in FULL:
            continue
        full_chunks += 1
        before = ores.copy()
        for section in A.BASE.section_list(root):
            sy = section.get("Y")
            if not isinstance(sy, int) or sy < MIN_SECTION or sy > MAX_SECTION:
                continue
            sections += 1
            A.count_section(section, ores, blocks)
        for kind in A.ORE_KINDS:
            if ores.get(kind, 0) > before.get(kind, 0):
                chunks_with[kind] += 1

    if full_chunks == 0:
        fail(f"no FULL chunks found; statuses={dict(status_counts)}")

    result = {
        "schema": 1,
        "world": "true-vanilla-26.2",
        "y": [-64, 319],
        "generated_chunk_candidates": len(coords),
        "full_chunks_scanned": full_chunks,
        "sections_scanned": sections,
        "status_counts": dict(sorted(status_counts.items())),
        "ore_blocks": {kind: ores.get(kind, 0) for kind in A.ORE_KINDS},
        "ore_blocks_per_full_chunk": {kind: round(ores.get(kind, 0) / full_chunks, 6) for kind in A.ORE_KINDS},
        "chunks_with_ore": {kind: chunks_with.get(kind, 0) for kind in A.ORE_KINDS},
        "ore_block_variants": {block: blocks.get(block, 0) for block in sorted(A.ORE_NAMES)},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
