#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][village persisted bbox] {message}")


def load_overworld_helpers(root: Path):
    path = root / "scripts/hash-never-overworld-generation-chunks.py"
    spec = importlib.util.spec_from_file_location("neverfolia_overworld_hash", path)
    if spec is None or spec.loader is None:
        fail(f"cannot load NBT helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def int_array(value: object) -> list[int] | None:
    if isinstance(value, dict):
        array = value.get("$int_array")
        if isinstance(array, list) and len(array) == 6 and all(isinstance(v, int) for v in array):
            return list(array)
    if isinstance(value, list) and len(value) == 6 and all(isinstance(v, int) for v in value):
        return list(value)
    return None


def collect_boxes(value: object) -> list[list[int]]:
    result: list[list[int]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in {"bb", "boundingbox", "bounding_box"}:
                box = int_array(child)
                if box is not None:
                    result.append(box)
            result.extend(collect_boxes(child))
    elif isinstance(value, list):
        for child in value:
            result.extend(collect_boxes(child))
    return result


def parse_locate(path: Path) -> tuple[str, int, int, int, int]:
    parts = path.read_text(encoding="utf-8").strip().split("\t")
    if len(parts) != 5:
        fail(f"locate TSV must contain structure,bx,bz,cx,cz: {parts}")
    target = parts[0]
    if not target.startswith("minecraft:village_"):
        fail(f"unexpected target: {target}")
    try:
        bx, bz, cx, cz = map(int, parts[1:])
    except ValueError as exc:
        fail(f"invalid locate coordinates: {exc}")
    return target, bx, bz, cx, cz


def audit(root: Path, world: Path, locate_path: Path, output: Path, source_sha: str) -> dict[str, object]:
    over = load_overworld_helpers(root)
    raw = over.BASE
    region = over.find_region_dir(world)
    target, bx, bz, cx, cz = parse_locate(locate_path)

    cache: dict[tuple[int, int], object | None] = {}

    def read_chunk(chunk_x: int, chunk_z: int):
        key = (chunk_x, chunk_z)
        if key not in cache:
            try:
                cache[key] = raw.read_chunk_nbt(region, chunk_x, chunk_z)
            except Exception:
                cache[key] = None
        return cache[key]

    starts: list[tuple[int, int, dict[str, object]]] = []
    for dz in range(-12, 13):
        for dx in range(-12, 13):
            chunk = read_chunk(cx + dx, cz + dz)
            if not isinstance(chunk, dict):
                continue
            starts_map = (chunk.get("structures") or {}).get("starts") or {}
            if not isinstance(starts_map, dict):
                continue
            start = starts_map.get(target)
            if isinstance(start, dict) and str(start.get("id", "")).upper() != "INVALID":
                starts.append((cx + dx, cz + dz, start))

    if not starts:
        fail(f"{target}: no persisted start near predicted locate chunk {cx},{cz}")
    starts.sort(key=lambda row: abs(row[0] - cx) + abs(row[1] - cz))
    start_cx, start_cz, start = starts[0]
    boxes = collect_boxes(start)
    if not boxes:
        fail(f"{target}: persisted start has no parseable Jigsaw bbox")

    min_x = min(box[0] for box in boxes)
    min_y = min(box[1] for box in boxes)
    min_z = min(box[2] for box in boxes)
    max_x = max(box[3] for box in boxes)
    max_y = max(box[4] for box in boxes)
    max_z = max(box[5] for box in boxes)

    water = 0
    missing = 0
    samples = 0
    first_water: list[list[int | str]] = []
    for z in range(min_z, max_z + 1):
        for x in range(min_x, max_x + 1):
            chunk = read_chunk(x // 16, z // 16)
            if chunk is None:
                missing += 1
                continue
            value = raw.block_at(chunk, x, 128, z)
            samples += 1
            if value == "minecraft:water":
                water += 1
                if len(first_water) < 32:
                    first_water.append([x, 128, z, value])

    report: dict[str, object] = {
        "schema": 3,
        "structure": target,
        "locate_block": [bx, bz],
        "predicted_chunk": [cx, cz],
        "start_chunk": [start_cx, start_cz],
        "bbox": [min_x, min_y, min_z, max_x, max_y, max_z],
        "bbox_width": max_x - min_x + 1,
        "bbox_depth": max_z - min_z + 1,
        "samples": samples,
        "missing": missing,
        "water_samples": water,
        "first_water": first_water,
        "policy": "persisted-jigsaw-bbox-all-blocks-zero-water-y128",
        "candidate_policy": "generated-jigsaw-bbox-all-columns-dry",
        "source_sha": source_sha,
        "save_barrier": "normal-stop-only",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

    if missing:
        fail(f"{target}: persisted bbox missing samples={missing}")
    if samples == 0:
        fail(f"{target}: persisted bbox has zero samples")
    if water:
        fail(f"{target}: submerged persisted bbox water={water}/{samples}")
    print(f"[NeverFolia][village persisted bbox] PASS {target}: water=0/{samples}")
    return report


def self_test() -> None:
    if int_array({"$int_array": [1, 2, 3, 4, 5, 6]}) != [1, 2, 3, 4, 5, 6]:
        fail("SELF-TEST: wrapped int array decode failed")
    if int_array([1, 2, 3, 4, 5, 6]) != [1, 2, 3, 4, 5, 6]:
        fail("SELF-TEST: plain int array decode failed")
    fixture = {"a": {"BB": {"$int_array": [1, 2, 3, 4, 5, 6]}}, "b": [{"bounding_box": [7, 8, 9, 10, 11, 12]}]}
    if collect_boxes(fixture) != [[1, 2, 3, 4, 5, 6], [7, 8, 9, 10, 11, 12]]:
        fail("SELF-TEST: recursive bbox collection failed")
    print("[NeverFolia][village persisted bbox] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--world", type=Path)
    parser.add_argument("--locate", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-sha", default="unknown")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.world is None or args.locate is None or args.output is None:
        parser.error("--world, --locate and --output are required")
    self_test()
    audit(args.root.resolve(), args.world.resolve(), args.locate.resolve(), args.output.resolve(), args.source_sha)


if __name__ == "__main__":
    main()
