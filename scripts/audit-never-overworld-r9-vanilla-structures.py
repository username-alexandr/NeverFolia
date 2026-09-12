#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
RAW_HASHER = ROOT / "scripts/hash-never-nether-chunks.py"
OVER_HASHER = ROOT / "scripts/hash-never-overworld-generation-chunks.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RAW = load_module(RAW_HASHER, "nr_raw_chunk_reader")
OVER = load_module(OVER_HASHER, "nr_overworld_reader")

AIRLIKE = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
WATERLIKE = {"minecraft:water", "minecraft:bubble_column"}
REPLACEABLE_BOTTOM = AIRLIKE | WATERLIKE | {
    "minecraft:seagrass",
    "minecraft:tall_seagrass",
    "minecraft:kelp",
    "minecraft:kelp_plant",
    "minecraft:sea_pickle",
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][R9 vanilla structure integrity] {message}")


def int_array(value) -> list[int]:
    if isinstance(value, dict) and isinstance(value.get("$int_array"), list):
        return [int(v) for v in value["$int_array"]]
    if isinstance(value, list):
        return [int(v) for v in value]
    raise ValueError(f"not an NBT int array: {value!r}")


@dataclass(frozen=True)
class Box:
    min_x: int
    min_y: int
    min_z: int
    max_x: int
    max_y: int
    max_z: int

    @classmethod
    def from_nbt(cls, value) -> "Box":
        raw = int_array(value)
        if len(raw) != 6:
            raise ValueError(f"structure BB must have 6 ints, got {raw}")
        return cls(*raw)

    @classmethod
    def union(cls, boxes: list["Box"]) -> "Box":
        if not boxes:
            raise ValueError("cannot union empty bbox list")
        return cls(
            min(box.min_x for box in boxes),
            min(box.min_y for box in boxes),
            min(box.min_z for box in boxes),
            max(box.max_x for box in boxes),
            max(box.max_y for box in boxes),
            max(box.max_z for box in boxes),
        )


def start_box(start: dict) -> tuple[Box, str, int]:
    """Resolve a persisted StructureStart bbox across Minecraft NBT layouts.

    Vanilla 26.2 starts do not necessarily persist a top-level BB. Their
    StructurePieces are stored under Children and each child owns a BB. In that
    layout the exact start bbox is the union of all valid child-piece boxes.
    """
    top = start.get("BB", start.get("bb"))
    if top is not None:
        return Box.from_nbt(top), "start.BB", 1

    children = start.get("Children", start.get("children", []))
    if not isinstance(children, list):
        raise ValueError(f"StructureStart Children is not a list: {type(children).__name__}")
    boxes: list[Box] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        raw = child.get("BB", child.get("bb"))
        if raw is None:
            continue
        boxes.append(Box.from_nbt(raw))
    if not boxes:
        raise ValueError(
            "StructureStart has neither a top-level BB nor child-piece BB values "
            f"(children={len(children)})"
        )
    return Box.union(boxes), "union(Children[*].BB)", len(boxes)


class WorldReader:
    def __init__(self, world: Path) -> None:
        self.region = OVER.find_region_dir(world)
        self.cache: dict[tuple[int, int], dict] = {}

    def chunk(self, cx: int, cz: int) -> dict:
        key = (cx, cz)
        if key not in self.cache:
            self.cache[key] = RAW.read_chunk_nbt(self.region, cx, cz)
        return self.cache[key]

    def block(self, x: int, y: int, z: int) -> str:
        return RAW.block_at(self.chunk(x // 16, z // 16), x, y, z)


def starts(root: dict) -> dict:
    structures = root.get("structures") or root.get("Structures") or {}
    value = structures.get("starts") or structures.get("Starts") or {}
    return value if isinstance(value, dict) else {}


def valid_start(value) -> bool:
    return isinstance(value, dict) and str(value.get("id", "")).upper() != "INVALID"


def find_start(reader: WorldReader, structure_id: str, block_x: int, block_z: int, radius_chunks: int = 8):
    center_x = block_x // 16
    center_z = block_z // 16
    matches: list[tuple[int, int, dict]] = []
    for dz in range(-radius_chunks, radius_chunks + 1):
        for dx in range(-radius_chunks, radius_chunks + 1):
            cx, cz = center_x + dx, center_z + dz
            try:
                root = reader.chunk(cx, cz)
            except FileNotFoundError:
                continue
            start = starts(root).get(structure_id)
            if valid_start(start):
                matches.append((cx, cz, start))
    if not matches:
        fail(
            f"generated start {structure_id} not found within {radius_chunks} chunks of "
            f"located block {block_x},{block_z}"
        )
    matches.sort(key=lambda row: (abs(row[0] - center_x) + abs(row[1] - center_z), row[0], row[1]))
    return matches[0]


def audit_swamp_hut(box: Box, block_at: Callable[[int, int, int], str]) -> dict:
    support_columns = []
    complete_columns = []
    start_y = box.min_y - 1
    min_y = -511

    for z in range(box.min_z, box.max_z + 1):
        for x in range(box.min_x, box.max_x + 1):
            if block_at(x, start_y, z) != "minecraft:oak_log":
                continue
            y = start_y
            length = 0
            while y >= min_y and block_at(x, y, z) == "minecraft:oak_log":
                length += 1
                y -= 1
            below = block_at(x, y, z) if y >= min_y else "<world-bottom>"
            row = {"x": x, "z": z, "top_y": start_y, "log_length": length, "below": below}
            support_columns.append(row)
            if below not in REPLACEABLE_BOTTOM:
                complete_columns.append(row)

    if len(support_columns) < 4:
        fail(
            f"swamp hut has only {len(support_columns)} oak support columns below bbox minY={box.min_y}; "
            "expected at least four"
        )
    if len(complete_columns) < 4:
        fail(
            "swamp hut supports terminate in air/water/replaceable blocks instead of solid bottom: "
            f"complete={len(complete_columns)}, all={support_columns[:12]}"
        )

    return {
        "support_columns": support_columns,
        "complete_support_columns": len(complete_columns),
        "passed": True,
    }


def count_blocks(box: Box, block_at: Callable[[int, int, int], str], wanted: set[str]) -> dict[str, int]:
    counts = {name: 0 for name in wanted}
    for y in range(box.min_y, box.max_y + 1):
        for z in range(box.min_z, box.max_z + 1):
            for x in range(box.min_x, box.max_x + 1):
                block = block_at(x, y, z)
                if block in counts:
                    counts[block] += 1
    return counts


def audit_ruined_portal(box: Box, block_at: Callable[[int, int, int], str]) -> dict:
    counts = count_blocks(
        box,
        block_at,
        {"minecraft:obsidian", "minecraft:crying_obsidian", "minecraft:magma_block"},
    )
    frame = counts["minecraft:obsidian"] + counts["minecraft:crying_obsidian"]
    if frame <= 0:
        fail(f"ruined portal bbox contains no obsidian/crying_obsidian after flood: {counts}")
    return {"block_counts": counts, "frame_blocks": frame, "passed": True}


def audit_trial_chambers(box: Box, block_at: Callable[[int, int, int], str]) -> dict:
    counts = count_blocks(
        box,
        block_at,
        {"minecraft:powder_snow", "minecraft:water", "minecraft:bubble_column"},
    )
    if counts["minecraft:powder_snow"]:
        fail(
            "trial chamber persisted powder_snow inside its generated bbox after R9 flood cleanup: "
            f"{counts['minecraft:powder_snow']} blocks"
        )
    return {"block_counts": counts, "passed": True}


def audit(world: Path, manifest: dict) -> dict:
    reader = WorldReader(world)
    contracts = {
        "minecraft:swamp_hut": audit_swamp_hut,
        "minecraft:ruined_portal": audit_ruined_portal,
        "minecraft:trial_chambers": audit_trial_chambers,
    }
    results = {}

    for structure_id, checker in contracts.items():
        entry = manifest.get(structure_id)
        if not isinstance(entry, dict):
            fail(f"manifest missing object for {structure_id}")
        try:
            block_x = int(entry["block_x"])
            block_z = int(entry["block_z"])
        except (KeyError, TypeError, ValueError) as exc:
            fail(f"manifest coordinates invalid for {structure_id}: {exc}")

        cx, cz, start = find_start(reader, structure_id, block_x, block_z)
        try:
            box, box_source, piece_boxes = start_box(start)
        except ValueError as exc:
            fail(f"{structure_id} start at {cx},{cz} bbox unresolved: {exc}")
        result = checker(box, reader.block)
        results[structure_id] = {
            "located_block": [block_x, block_z],
            "start_chunk": [cx, cz],
            "bbox": [box.min_x, box.min_y, box.min_z, box.max_x, box.max_y, box.max_z],
            "bbox_source": box_source,
            "piece_bbox_count": piece_boxes,
            **result,
        }

    return {
        "schema": 2,
        "contract": "R9 naturally generated vanilla structure flood integrity",
        "structures": results,
        "passed": True,
    }


def self_test() -> None:
    if int_array({"$int_array": [1, 2, 3, 4, 5, 6]}) != [1, 2, 3, 4, 5, 6]:
        fail("SELF-TEST: NBT int-array decoding failed")
    if Box.from_nbt({"$int_array": [1, 2, 3, 4, 5, 6]}).min_y != 2:
        fail("SELF-TEST: bbox parsing failed")

    top_box, source, pieces = start_box({"BB": {"$int_array": [1, 2, 3, 4, 5, 6]}})
    if top_box != Box(1, 2, 3, 4, 5, 6) or source != "start.BB" or pieces != 1:
        fail("SELF-TEST: top-level StructureStart BB resolution failed")
    child_box, source, pieces = start_box(
        {
            "Children": [
                {"BB": {"$int_array": [10, 20, 30, 15, 25, 35]}},
                {"BB": {"$int_array": [4, 18, 28, 12, 27, 40]}},
            ]
        }
    )
    if child_box != Box(4, 18, 28, 15, 27, 40) or source != "union(Children[*].BB)" or pieces != 2:
        fail("SELF-TEST: child-piece StructureStart BB union failed")

    # Synthetic hut: four supports descend through waterline and terminate on stone.
    blocks: dict[tuple[int, int, int], str] = {}
    box = Box(0, 129, 0, 6, 136, 8)
    for x, z in ((1, 2), (5, 2), (1, 7), (5, 7)):
        for y in range(128, 124, -1):
            blocks[(x, y, z)] = "minecraft:oak_log"
        blocks[(x, 124, z)] = "minecraft:stone"
    synthetic = lambda x, y, z: blocks.get((x, y, z), "minecraft:water")
    hut = audit_swamp_hut(box, synthetic)
    if hut["complete_support_columns"] != 4:
        fail("SELF-TEST: complete swamp-hut supports were not recognized")

    broken = dict(blocks)
    broken.pop((5, 125, 7))
    broken_reader = lambda x, y, z: broken.get((x, y, z), "minecraft:water")
    try:
        audit_swamp_hut(box, broken_reader)
    except SystemExit:
        pass
    else:
        fail("SELF-TEST: support terminating in water was accepted")

    portal_blocks = {(0, 64, 0): "minecraft:obsidian"}
    portal = audit_ruined_portal(Box(0, 64, 0, 1, 65, 1), lambda x, y, z: portal_blocks.get((x, y, z), "minecraft:air"))
    if portal["frame_blocks"] != 1:
        fail("SELF-TEST: ruined portal frame was not counted")

    trial_box = Box(0, -20, 0, 1, -19, 1)
    clean_trial = audit_trial_chambers(trial_box, lambda x, y, z: "minecraft:air")
    if not clean_trial["passed"]:
        fail("SELF-TEST: clean trial chamber failed")
    try:
        audit_trial_chambers(
            trial_box,
            lambda x, y, z: "minecraft:powder_snow" if (x, y, z) == (0, -20, 0) else "minecraft:air",
        )
    except SystemExit:
        pass
    else:
        fail("SELF-TEST: powder snow inside trial chamber was accepted")

    print("[NeverFolia][R9 vanilla structure integrity] SELF-TEST OK")
    print("  bbox: direct start.BB or exact union of persisted Children[*].BB")
    print("  swamp hut: >=4 oak supports must terminate on solid bottom")
    print("  ruined portal: obsidian/crying_obsidian frame must survive")
    print("  trial chambers: powder_snow inside generated bbox is forbidden")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit naturally generated vanilla structures after the NeverOverworld R9 flood pass")
    parser.add_argument("--world", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.world is None or args.manifest is None:
        parser.error("--world and --manifest are required unless --self-test is used")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    result = audit(args.world.resolve(), manifest)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    print(rendered, end="")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    main()
