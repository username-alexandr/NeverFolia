#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_AUDITOR = ROOT / "scripts/audit-never-overworld-native-geology.py"

spec = importlib.util.spec_from_file_location("nr_visible_ore_base", BASE_AUDITOR)
if spec is None or spec.loader is None:
    raise SystemExit(f"cannot import native geology auditor: {BASE_AUDITOR}")
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)

FULL_STATUSES = {"full", "minecraft:full"}
AIR_BLOCKS = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
FLUID_EXPOSURE_BLOCKS = {
    "minecraft:water",
    "minecraft:lava",
    "minecraft:bubble_column",
    "minecraft:kelp",
    "minecraft:kelp_plant",
    "minecraft:seagrass",
    "minecraft:tall_seagrass",
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld visible ore audit] {message}")


def chunk_status(root: dict) -> str:
    value = root.get("Status", root.get("status", ""))
    return value if isinstance(value, str) else ""


def exposure_kind(block: str) -> str | None:
    if block in AIR_BLOCKS:
        return "air"
    if block in FLUID_EXPOSURE_BLOCKS:
        return "fluid"
    return None


def exposed_at(root: dict, x: int, y: int, z: int) -> tuple[bool, bool]:
    air = False
    fluid = False
    for dx, dy, dz in ((-1,0,0),(1,0,0),(0,-1,0),(0,1,0),(0,0,-1),(0,0,1)):
        kind = exposure_kind(A.BASE.block_at(root, x + dx, y + dy, z + dz))
        if kind == "air":
            air = True
        elif kind == "fluid":
            fluid = True
    return air, fluid


def audit(world: Path, max_chunks: int, min_y: int, max_y: int) -> dict:
    region = A.NR.find_region_dir(world)
    total: Counter[str] = Counter()
    exposed: Counter[str] = Counter()
    air_exposed: Counter[str] = Counter()
    fluid_exposed: Counter[str] = Counter()
    chunks_with_ore: Counter[str] = Counter()
    scanned = 0
    scanned_columns = 0

    for cx, cz in A.generated_chunks(region):
        if scanned >= max_chunks:
            break
        try:
            root = A.BASE.read_chunk_nbt(region, cx, cz)
        except Exception:
            continue
        if chunk_status(root) not in FULL_STATUSES:
            continue
        scanned += 1
        before = total.copy()
        base_x = cx * 16
        base_z = cz * 16
        for lz in range(1, 15):
            z = base_z + lz
            for lx in range(1, 15):
                x = base_x + lx
                scanned_columns += 1
                for y in range(min_y, max_y + 1):
                    block = A.BASE.block_at(root, x, y, z)
                    ore = A.ORE_NAMES.get(block)
                    if ore is None:
                        continue
                    total[ore] += 1
                    air, fluid = exposed_at(root, x, y, z)
                    if air or fluid:
                        exposed[ore] += 1
                    if air:
                        air_exposed[ore] += 1
                    if fluid:
                        fluid_exposed[ore] += 1
        for ore in A.ORE_KINDS:
            if total.get(ore, 0) > before.get(ore, 0):
                chunks_with_ore[ore] += 1

    if scanned == 0:
        fail("no FULL chunks were available")

    ores = {}
    for ore in A.ORE_KINDS:
        t = total.get(ore, 0)
        e = exposed.get(ore, 0)
        ores[ore] = {
            "total_blocks": t,
            "total_blocks_per_full_chunk_interior": round(t / scanned, 6),
            "exposed_blocks": e,
            "exposed_blocks_per_full_chunk_interior": round(e / scanned, 6),
            "exposed_fraction": round(e / t, 6) if t else 0.0,
            "air_exposed_blocks": air_exposed.get(ore, 0),
            "fluid_exposed_blocks": fluid_exposed.get(ore, 0),
            "chunks_with_ore": chunks_with_ore.get(ore, 0),
        }

    return {
        "schema": 1,
        "world": str(world),
        "y_range": [min_y, max_y],
        "sample": "FULL chunks; 14x14 interior columns only",
        "full_chunks_scanned": scanned,
        "interior_columns_scanned": scanned_columns,
        "air_blocks": sorted(AIR_BLOCKS),
        "fluid_exposure_blocks": sorted(FLUID_EXPOSURE_BLOCKS),
        "ores": ores,
        "all_ore_blocks": sum(total.values()),
        "all_exposed_ore_blocks": sum(exposed.values()),
        "all_exposed_fraction": round(sum(exposed.values()) / sum(total.values()), 6) if total else 0.0,
    }


def self_test() -> None:
    if exposure_kind("minecraft:cave_air") != "air":
        fail("SELF-TEST: cave_air not classified")
    if exposure_kind("minecraft:water") != "fluid":
        fail("SELF-TEST: water not classified")
    if exposure_kind("minecraft:stone") is not None:
        fail("SELF-TEST: stone incorrectly classified as exposure")
    if "minecraft:diamond_ore" not in A.ORE_NAMES or A.ORE_NAMES["minecraft:diamond_ore"] != "diamond":
        fail("SELF-TEST: ore mapping unavailable")
    print("[NeverFolia][NeverOverworld visible ore audit] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path)
    parser.add_argument("--max-chunks", type=int, default=256)
    parser.add_argument("--min-y", type=int, default=-64)
    parser.add_argument("--max-y", type=int, default=319)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.world is None or args.output is None:
        parser.error("--world and --output are required")
    result = audit(args.world.resolve(), args.max_chunks, args.min_y, args.max_y)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
