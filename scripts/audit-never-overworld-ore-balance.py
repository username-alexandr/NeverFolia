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
TRANSITION_MIN_SECTION = -6     # Y=-96
TRANSITION_MAX_SECTION = -5     # Y=-65
TRANSITION_BOUNDARY_Y = -96     # native geology may legitimately write this one layer
VANILLA_MIN_SECTION = -4        # Y=-64
VANILLA_MAX_SECTION = 19        # Y=319
BAND_HEIGHT = 32
FULL_STATUSES = {"full", "minecraft:full"}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld ore balance audit] {message}")


def sample_key(coord: tuple[int, int]) -> bytes:
    cx, cz = coord
    return hashlib.sha256(f"NR-ORE-BALANCE:{cx},{cz}".encode("ascii")).digest()


def chunk_status(root: dict) -> str:
    value = root.get("Status", root.get("status", ""))
    return value if isinstance(value, str) else ""


def generated_coords(region: Path) -> list[tuple[int, int]]:
    coords = list(dict.fromkeys(A.generated_chunks(region)))
    coords.sort(key=sample_key)
    return coords


def full_coords(region: Path) -> tuple[set[tuple[int, int]], Counter[str]]:
    result: set[tuple[int, int]] = set()
    statuses: Counter[str] = Counter()
    for cx, cz in generated_coords(region):
        try:
            root = A.BASE.read_chunk_nbt(region, cx, cz)
        except Exception:
            continue
        status = chunk_status(root)
        statuses[status or "<missing>"] += 1
        if status in FULL_STATUSES:
            result.add((cx, cz))
    return result, statuses


def per_chunk(counts: Counter[str], chunks: int) -> dict[str, float]:
    return {kind: round(counts.get(kind, 0) / chunks, 6) for kind in A.ORE_KINDS}


def ratio(deep: Counter[str], vanilla: Counter[str]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for kind in A.ORE_KINDS:
        v = vanilla.get(kind, 0)
        result[kind] = None if v <= 0 else round(deep.get(kind, 0) / v, 6)
    return result


def band_start_for_y(y: int) -> int:
    return (y // BAND_HEIGHT) * BAND_HEIGHT


def band_label(start_y: int) -> str:
    return f"Y={start_y}..{start_y + BAND_HEIGHT - 1}"


def count_range(
    root: dict,
    min_section: int,
    max_section: int,
    counts: Counter[str],
    blocks: Counter[str],
    bands: dict[int, Counter[str]] | None = None,
) -> int:
    sections = 0
    for section in A.BASE.section_list(root):
        sy = section.get("Y")
        if not isinstance(sy, int) or sy < min_section or sy > max_section:
            continue
        sections += 1
        section_counts: Counter[str] = Counter()
        section_blocks: Counter[str] = Counter()
        A.count_section(section, section_counts, section_blocks)
        counts.update(section_counts)
        blocks.update(section_blocks)
        if bands is not None:
            start_y = band_start_for_y(sy * 16)
            bands.setdefault(start_y, Counter()).update(section_counts)
    return sections


def serialize_bands(
    bands: dict[int, Counter[str]],
    chunks: int,
    min_y: int,
    max_y: int,
) -> dict[str, dict]:
    result: dict[str, dict] = {}
    start = band_start_for_y(min_y)
    stop = band_start_for_y(max_y)
    while start <= stop:
        counts = bands.get(start, Counter())
        result[band_label(start)] = {
            "ore_blocks": {kind: counts.get(kind, 0) for kind in A.ORE_KINDS},
            "ore_blocks_per_full_chunk": per_chunk(counts, chunks),
        }
        start += BAND_HEIGHT
    return result


def count_boundary_y(root: dict, cx: int, cz: int, y: int) -> Counter[str]:
    counts: Counter[str] = Counter()
    base_x = cx * 16
    base_z = cz * 16
    for lz in range(16):
        for lx in range(16):
            block = A.BASE.block_at(root, base_x + lx, y, base_z + lz)
            kind = A.ORE_NAMES.get(block)
            if kind is not None:
                counts[kind] += 1
    return counts


def subtract_nonnegative(total: Counter[str], allowed: Counter[str]) -> Counter[str]:
    result: Counter[str] = Counter()
    for kind in A.ORE_KINDS:
        value = total.get(kind, 0) - allowed.get(kind, 0)
        if value > 0:
            result[kind] = value
    return result


def audit(world: Path, max_chunks: int, vanilla_world: Path | None = None) -> dict:
    deep_region = A.NR.find_region_dir(world)
    vanilla_region = A.NR.find_region_dir(vanilla_world) if vanilla_world is not None else deep_region

    deep_full, deep_statuses = full_coords(deep_region)
    vanilla_full, vanilla_statuses = full_coords(vanilla_region)
    common = sorted(deep_full & vanilla_full, key=sample_key)[:max_chunks]
    if not common:
        fail("no common FULL chunks between NeverOverworld and vanilla reference worlds")

    deep: Counter[str] = Counter()
    deep_blocks: Counter[str] = Counter()
    deep_bands: dict[int, Counter[str]] = {}
    transition: Counter[str] = Counter()
    transition_blocks: Counter[str] = Counter()
    transition_boundary: Counter[str] = Counter()
    vanilla: Counter[str] = Counter()
    vanilla_blocks: Counter[str] = Counter()
    vanilla_bands: dict[int, Counter[str]] = {}
    chunks_with_deep = Counter()
    chunks_with_vanilla = Counter()
    deep_sections = 0
    transition_sections = 0
    vanilla_sections = 0
    scanned = 0

    for cx, cz in common:
        try:
            deep_root = A.BASE.read_chunk_nbt(deep_region, cx, cz)
            vanilla_root = A.BASE.read_chunk_nbt(vanilla_region, cx, cz)
        except Exception:
            continue
        if chunk_status(deep_root) not in FULL_STATUSES or chunk_status(vanilla_root) not in FULL_STATUSES:
            continue
        scanned += 1
        deep_before = deep.copy()
        vanilla_before = vanilla.copy()
        deep_sections += count_range(
            deep_root,
            DEEP_MIN_SECTION,
            DEEP_MAX_SECTION,
            deep,
            deep_blocks,
            deep_bands,
        )
        transition_sections += count_range(
            deep_root,
            TRANSITION_MIN_SECTION,
            TRANSITION_MAX_SECTION,
            transition,
            transition_blocks,
        )
        transition_boundary.update(count_boundary_y(deep_root, cx, cz, TRANSITION_BOUNDARY_Y))
        vanilla_sections += count_range(
            vanilla_root,
            VANILLA_MIN_SECTION,
            VANILLA_MAX_SECTION,
            vanilla,
            vanilla_blocks,
            vanilla_bands,
        )
        for kind in A.ORE_KINDS:
            if deep.get(kind, 0) > deep_before.get(kind, 0):
                chunks_with_deep[kind] += 1
            if vanilla.get(kind, 0) > vanilla_before.get(kind, 0):
                chunks_with_vanilla[kind] += 1

    if scanned == 0:
        fail("common FULL chunk set became unreadable")
    if vanilla_sections == 0 or deep_sections == 0 or transition_sections == 0:
        fail(
            "expected deep, transition and vanilla sections, got "
            f"deep={deep_sections} transition={transition_sections} vanilla={vanilla_sections}"
        )

    transition_leak = subtract_nonnegative(transition, transition_boundary)
    transition_isolated = not any(transition_leak.values())

    result = {
        "schema": 4,
        "sample_method": "common-full-chunks-sha256-v4",
        "reference_mode": "separate-vanilla-world" if vanilla_world is not None else "same-world-upper-range",
        "full_chunks_requested": max_chunks,
        "neveroverworld_full_chunks_available": len(deep_full),
        "vanilla_full_chunks_available": len(vanilla_full),
        "common_full_chunks_available": len(deep_full & vanilla_full),
        "common_full_chunks_scanned": scanned,
        "neveroverworld_status_counts": dict(sorted(deep_statuses.items())),
        "vanilla_status_counts": dict(sorted(vanilla_statuses.items())),
        "deep_y": [-512, -97],
        "transition_y": [-96, -65],
        "transition_native_boundary_y": TRANSITION_BOUNDARY_Y,
        "vanilla_reference_y": [-64, 319],
        "deep_sections_scanned": deep_sections,
        "transition_sections_scanned": transition_sections,
        "vanilla_sections_scanned": vanilla_sections,
        "deep_ore_blocks": {kind: deep.get(kind, 0) for kind in A.ORE_KINDS},
        "transition_resource_ore_blocks": {kind: transition.get(kind, 0) for kind in A.ORE_KINDS},
        "transition_boundary_y_minus_96_ore_blocks": {
            kind: transition_boundary.get(kind, 0) for kind in A.ORE_KINDS
        },
        "transition_resource_ore_leak_blocks_y_minus_95_to_minus_65": {
            kind: transition_leak.get(kind, 0) for kind in A.ORE_KINDS
        },
        "resource_ore_source_isolation_satisfied": transition_isolated,
        "vanilla_reference_ore_blocks": {kind: vanilla.get(kind, 0) for kind in A.ORE_KINDS},
        "deep_ore_blocks_per_full_chunk": per_chunk(deep, scanned),
        "vanilla_reference_ore_blocks_per_full_chunk": per_chunk(vanilla, scanned),
        "deep_to_vanilla_ratio": ratio(deep, vanilla),
        "chunks_with_deep_ore": {kind: chunks_with_deep.get(kind, 0) for kind in A.ORE_KINDS},
        "chunks_with_vanilla_reference_ore": {
            kind: chunks_with_vanilla.get(kind, 0) for kind in A.ORE_KINDS
        },
        "deep_ore_block_variants": {block: deep_blocks.get(block, 0) for block in sorted(A.ORE_NAMES)},
        "transition_ore_block_variants": {
            block: transition_blocks.get(block, 0) for block in sorted(A.ORE_NAMES)
        },
        "vanilla_reference_ore_block_variants": {
            block: vanilla_blocks.get(block, 0) for block in sorted(A.ORE_NAMES)
        },
        "deep_vertical_profile_32_blocks": serialize_bands(deep_bands, scanned, -512, -97),
        "vanilla_vertical_profile_32_blocks": serialize_bands(vanilla_bands, scanned, -64, 319),
    }
    return result


def self_test() -> None:
    coords = [(0, 0), (1, 1), (-1, 7), (55, -9)]
    first = sorted(coords, key=sample_key)
    second = sorted(reversed(coords), key=sample_key)
    if first != second:
        fail("SELF-TEST: deterministic sample ordering is unstable")
    if chunk_status({"Status": "minecraft:full"}) != "minecraft:full":
        fail("SELF-TEST: canonical Status field not read")
    if chunk_status({"status": "full"}) != "full":
        fail("SELF-TEST: lowercase status field not read")
    d = Counter({"iron": 20, "diamond": 5})
    v = Counter({"iron": 10, "diamond": 0})
    r = ratio(d, v)
    if r["iron"] != 2.0 or r["diamond"] is not None:
        fail("SELF-TEST: ratio calculation failed")
    if band_start_for_y(-512) != -512 or band_start_for_y(-481) != -512:
        fail("SELF-TEST: deep 32-block band mapping failed")
    if band_start_for_y(-96) != -96 or band_start_for_y(-65) != -96:
        fail("SELF-TEST: transition 32-block band mapping failed")
    if band_start_for_y(-64) != -64 or band_start_for_y(319) != 288:
        fail("SELF-TEST: vanilla 32-block band mapping failed")
    total = Counter({"iron": 7, "diamond": 2})
    boundary = Counter({"iron": 7, "diamond": 1})
    leak = subtract_nonnegative(total, boundary)
    if leak.get("iron", 0) != 0 or leak.get("diamond", 0) != 1:
        fail("SELF-TEST: transition leak subtraction failed")
    print("[NeverFolia][NeverOverworld ore balance audit] TRUE-VANILLA FULL-CHUNK + VERTICAL PROFILE SELF-TEST OK")
    print("  transition source isolation: no standard ore is allowed at Y=-95..-65")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare NR deep native ore density with a true vanilla 26.2 FULL-chunk reference"
    )
    parser.add_argument("--world", type=Path)
    parser.add_argument("--vanilla-world", type=Path)
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

    result = audit(
        args.world.resolve(),
        args.max_chunks,
        args.vanilla_world.resolve() if args.vanilla_world is not None else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
