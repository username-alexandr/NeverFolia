#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import Counter
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


RAW = load_module(RAW_HASHER, "neverfolia_raw_chunk_reader")
OVER = load_module(OVER_HASHER, "neverfolia_overworld_reader")

REGION_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")
AIR = {
    "minecraft:air",
    "minecraft:cave_air",
    "minecraft:void_air",
}
WATERLIKE = {
    "minecraft:water",
    "minecraft:bubble_column",
}
FLUID = WATERLIKE | {"minecraft:lava"}
# Decoration that may sit above the actual drowned ground. Ignore it while
# resolving the first terrain/substrate block in a column.
OVERLAY = {
    "minecraft:seagrass",
    "minecraft:tall_seagrass",
    "minecraft:kelp",
    "minecraft:kelp_plant",
    "minecraft:sea_pickle",
    "minecraft:sugar_cane",
}
FORBIDDEN_LIVING_SURFACE = {
    "minecraft:grass_block",
    "minecraft:podzol",
    "minecraft:mycelium",
    "minecraft:dirt_path",
    "minecraft:moss_block",
    "minecraft:snow_block",
    "minecraft:rooted_dirt",
}
FORBIDDEN_DROWNED_REMAINS = {
    "minecraft:mushroom_stem",
    "minecraft:red_mushroom_block",
    "minecraft:brown_mushroom_block",
}
DROWNED_PALETTE = {
    "minecraft:dirt",
    "minecraft:coarse_dirt",
    "minecraft:mud",
    "minecraft:gravel",
    "minecraft:sand",
    "minecraft:clay",
    "minecraft:stone",
    "minecraft:andesite",
}
POWDER_SNOW = "minecraft:powder_snow"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld drowned surface audit] {message}")


def generated_chunks(region_dir: Path):
    for path in sorted(region_dir.glob("r.*.*.mca")):
        match = REGION_RE.match(path.name)
        if not match:
            continue
        rx, rz = map(int, match.groups())
        header = path.read_bytes()[:4096]
        if len(header) < 4096:
            continue
        for index in range(1024):
            packed = int.from_bytes(header[index * 4 : index * 4 + 4], "big")
            if packed == 0:
                continue
            lx = index & 31
            lz = index >> 5
            yield rx * 32 + lx, rz * 32 + lz


def inspect_drowned_column(
    get_block: Callable[[int], str],
    flood_level: int,
    min_scan_y: int,
) -> dict | None:
    """Inspect the persisted vertical water column, not a cached heightmap.

    R9 contract: if Y=flood_level is source water, every open cell above the
    first solid/substrate must remain water/aquatic decoration. Air in that
    interval is the exact field defect that produced visible underwater voids
    and dry cells above magma. Powder snow is also invalid below the flood plane.
    """
    if get_block(flood_level) != "minecraft:water":
        return None

    air_gaps: list[tuple[int, str]] = []
    powder_snow: list[int] = []
    non_water_fluids: list[tuple[int, str]] = []
    substrate: tuple[int, str] | None = None

    for y in range(flood_level - 1, min_scan_y - 1, -1):
        block = get_block(y)
        if block in WATERLIKE or block in OVERLAY:
            continue
        if block in AIR:
            air_gaps.append((y, block))
            continue
        if block == "minecraft:lava":
            non_water_fluids.append((y, block))
            continue
        if block == POWDER_SNOW:
            powder_snow.append(y)
        substrate = (y, block)
        break

    return {
        "substrate": substrate,
        "air_gaps": air_gaps,
        "powder_snow": powder_snow,
        "non_water_fluids": non_water_fluids,
    }


def resolve_drowned_column(root: dict, wx: int, wz: int, flood_level: int, min_scan_y: int) -> dict | None:
    return inspect_drowned_column(
        lambda y: RAW.block_at(root, wx, y, wz),
        flood_level,
        min_scan_y,
    )


def audit(world: Path, max_chunks: int, flood_level: int = 128, min_scan_y: int = -96) -> dict:
    region = OVER.find_region_dir(world)
    chunks_scanned = 0
    drowned_columns = 0
    unresolved_deep_columns = 0
    air_gap_columns = 0
    air_gap_blocks = 0
    powder_snow_columns = 0
    non_water_fluid_columns = 0
    material_counts: Counter[str] = Counter()
    forbidden_living: Counter[str] = Counter()
    forbidden_remains: Counter[str] = Counter()
    drowned_palette: Counter[str] = Counter()
    depth_bands: Counter[str] = Counter()
    air_gap_examples: list[dict] = []
    powder_snow_examples: list[dict] = []
    non_water_fluid_examples: list[dict] = []

    for cx, cz in generated_chunks(region):
        if chunks_scanned >= max_chunks:
            break
        try:
            root = RAW.read_chunk_nbt(region, cx, cz)
        except Exception:
            continue
        chunks_scanned += 1
        base_x = cx * 16
        base_z = cz * 16
        for lz in range(16):
            for lx in range(16):
                wx = base_x + lx
                wz = base_z + lz
                inspected = resolve_drowned_column(root, wx, wz, flood_level, min_scan_y)
                if inspected is None:
                    continue
                drowned_columns += 1

                air_gaps = inspected["air_gaps"]
                if air_gaps:
                    air_gap_columns += 1
                    air_gap_blocks += len(air_gaps)
                    if len(air_gap_examples) < 24:
                        air_gap_examples.append(
                            {
                                "x": wx,
                                "z": wz,
                                "cells": [[y, block] for y, block in air_gaps[:12]],
                            }
                        )

                powder = inspected["powder_snow"]
                if powder:
                    powder_snow_columns += 1
                    if len(powder_snow_examples) < 24:
                        powder_snow_examples.append({"x": wx, "z": wz, "y": powder[0]})

                non_water = inspected["non_water_fluids"]
                if non_water:
                    non_water_fluid_columns += 1
                    if len(non_water_fluid_examples) < 24:
                        non_water_fluid_examples.append(
                            {
                                "x": wx,
                                "z": wz,
                                "cells": [[y, block] for y, block in non_water[:12]],
                            }
                        )

                substrate = inspected["substrate"]
                if substrate is None:
                    # Extended-height terrain can legitimately place the first
                    # solid bottom below this audit's configured min_scan_y.
                    unresolved_deep_columns += 1
                    continue

                y, block = substrate
                material_counts[block] += 1
                depth = flood_level - y
                if depth <= 6:
                    depth_bands["shallow_1_6"] += 1
                elif depth <= 24:
                    depth_bands["mid_7_24"] += 1
                else:
                    depth_bands["deep_25_plus"] += 1
                if block in FORBIDDEN_LIVING_SURFACE:
                    forbidden_living[block] += 1
                if block in FORBIDDEN_DROWNED_REMAINS:
                    forbidden_remains[block] += 1
                if block in DROWNED_PALETTE:
                    drowned_palette[block] += 1

    if chunks_scanned == 0:
        fail("no generated chunks were readable")
    if drowned_columns == 0:
        fail("no Y=128 flooded columns were found in the generated sample")
    if air_gap_columns:
        fail(
            "open flooded columns contain persisted air before the first solid bottom: "
            f"columns={air_gap_columns}, air_blocks={air_gap_blocks}, examples={air_gap_examples[:8]}"
        )
    if powder_snow_columns:
        fail(
            "powder_snow survived below the Y=128 open-water plane: "
            f"columns={powder_snow_columns}, examples={powder_snow_examples[:8]}"
        )
    if forbidden_living:
        details = ", ".join(f"{name}={count}" for name, count in sorted(forbidden_living.items()))
        fail(f"living pre-flood surface survived underwater: {details}")
    if forbidden_remains:
        details = ", ".join(f"{name}={count}" for name, count in sorted(forbidden_remains.items()))
        fail(f"drowned giant-mushroom remains survived flood cleanup: {details}")

    distinct_weathered = sum(1 for count in drowned_palette.values() if count > 0)
    # The field complaint was a uniform living-grass carpet. Require a visibly
    # heterogeneous drowned substrate in CI, while allowing biome/seed variation.
    if distinct_weathered < 3:
        fail(
            "drowned substrate lacks material diversity: "
            f"only {distinct_weathered} expected sediment/substrate materials observed"
        )

    return {
        "schema": 2,
        "flood_level": flood_level,
        "min_scan_y": min_scan_y,
        "chunks_scanned": chunks_scanned,
        "drowned_columns": drowned_columns,
        "unresolved_deep_columns": unresolved_deep_columns,
        "open_water_air_gap_columns": air_gap_columns,
        "open_water_air_gap_blocks": air_gap_blocks,
        "powder_snow_columns": powder_snow_columns,
        "non_water_fluid_columns": non_water_fluid_columns,
        "non_water_fluid_examples": non_water_fluid_examples,
        "forbidden_living_surface": dict(sorted(forbidden_living.items())),
        "forbidden_drowned_remains": dict(sorted(forbidden_remains.items())),
        "depth_bands": dict(sorted(depth_bands.items())),
        "drowned_palette": dict(sorted(drowned_palette.items())),
        "distinct_expected_palette_materials": distinct_weathered,
        "top_materials": dict(material_counts.most_common(24)),
    }


def self_test() -> None:
    if "minecraft:grass_block" not in FORBIDDEN_LIVING_SURFACE:
        fail("SELF-TEST: grass_block must be forbidden underwater")
    for block in ("minecraft:mud", "minecraft:gravel", "minecraft:sand", "minecraft:clay", "minecraft:stone"):
        if block not in DROWNED_PALETTE:
            fail(f"SELF-TEST: expected drowned palette material missing: {block}")
    if FORBIDDEN_LIVING_SURFACE & DROWNED_PALETTE:
        fail("SELF-TEST: living and weathered material sets overlap")
    if not FORBIDDEN_DROWNED_REMAINS.issuperset({"minecraft:mushroom_stem", "minecraft:red_mushroom_block"}):
        fail("SELF-TEST: giant mushroom cleanup set drifted")

    def synthetic(mapping: dict[int, str], default: str = "minecraft:stone") -> Callable[[int], str]:
        return lambda y: mapping.get(y, default)

    good = inspect_drowned_column(
        synthetic(
            {
                128: "minecraft:water",
                127: "minecraft:water",
                126: "minecraft:seagrass",
                125: "minecraft:water",
                124: "minecraft:sand",
            }
        ),
        128,
        120,
    )
    if good is None or good["air_gaps"] or good["substrate"] != (124, "minecraft:sand"):
        fail(f"SELF-TEST: healthy drowned column misclassified: {good}")

    gap = inspect_drowned_column(
        synthetic(
            {
                128: "minecraft:water",
                127: "minecraft:water",
                126: "minecraft:cave_air",
                125: "minecraft:water",
                124: "minecraft:magma_block",
            }
        ),
        128,
        120,
    )
    if gap is None or gap["air_gaps"] != [(126, "minecraft:cave_air")]:
        fail(f"SELF-TEST: underwater air gap was not detected: {gap}")

    powder = inspect_drowned_column(
        synthetic({128: "minecraft:water", 127: "minecraft:powder_snow"}),
        128,
        120,
    )
    if powder is None or powder["powder_snow"] != [127]:
        fail(f"SELF-TEST: submerged powder snow was not detected: {powder}")

    dry = inspect_drowned_column(
        synthetic({128: "minecraft:air"}),
        128,
        120,
    )
    if dry is not None:
        fail("SELF-TEST: dry Y=128 column must not enter drowned audit")

    print("[NeverFolia][NeverOverworld drowned surface audit] R9 INTEGRITY SELF-TEST OK")
    print("  open-water air gaps: forbidden")
    print("  submerged powder snow: forbidden")
    print("  deep bottoms below scan floor: diagnostic, not false-positive failure")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit flooded NeverOverworld surface weathering and open-water integrity in persisted chunk NBT")
    parser.add_argument("--world", type=Path)
    parser.add_argument("--max-chunks", type=int, default=1024)
    parser.add_argument("--flood-level", type=int, default=128)
    parser.add_argument("--min-scan-y", type=int, default=-96)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.world is None:
        parser.error("--world is required unless --self-test is used")
    if args.max_chunks <= 0:
        parser.error("--max-chunks must be positive")

    result = audit(args.world.resolve(), args.max_chunks, args.flood_level, args.min_scan_y)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
