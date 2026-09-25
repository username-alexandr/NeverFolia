#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOPOLOGY = ROOT / "scripts/audit-never-overworld-cave-topology.py"

spec = importlib.util.spec_from_file_location("nr_flood_topology", TOPOLOGY)
if spec is None or spec.loader is None:
    raise SystemExit(f"cannot import NeverOverworld topology helpers: {TOPOLOGY}")
TOPO = importlib.util.module_from_spec(spec)
spec.loader.exec_module(TOPO)
BASE = TOPO.BASE

FLOOD_Y = 128
SCAN_MIN_Y = 65
ORE_MAX_Y = 135

RAILS = {
    "minecraft:rail",
    "minecraft:powered_rail",
    "minecraft:detector_rail",
    "minecraft:activator_rail",
}
SHORE_FLORA = {"minecraft:sugar_cane", "minecraft:lily_pad"}
ORES = {
    "minecraft:coal_ore", "minecraft:deepslate_coal_ore",
    "minecraft:iron_ore", "minecraft:deepslate_iron_ore",
    "minecraft:copper_ore", "minecraft:deepslate_copper_ore",
    "minecraft:gold_ore", "minecraft:deepslate_gold_ore",
    "minecraft:redstone_ore", "minecraft:deepslate_redstone_ore",
    "minecraft:lapis_ore", "minecraft:deepslate_lapis_ore",
    "minecraft:diamond_ore", "minecraft:deepslate_diamond_ore",
    "minecraft:emerald_ore", "minecraft:deepslate_emerald_ore",
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld flood surface audit] {message}")


def is_tree_block(name: str) -> bool:
    return (
        name.endswith("_log")
        or name.endswith("_wood")
        or name.endswith("_stem")
        or name.endswith("_hyphae")
        or name.endswith("_leaves")
        or name in {"minecraft:mangrove_roots", "minecraft:muddy_mangrove_roots"}
    )


def block_at(decoded: dict[int, list[str]], y: int, lx: int, lz: int) -> str:
    sy = y // 16
    local_y = y - sy * 16
    return decoded[sy][(local_y << 8) | (lz << 4) | lx]


def audit(world: Path, max_chunks: int) -> dict:
    region = TOPO.NR.find_region_dir(world)
    scanned = 0
    records_seen = 0
    skipped_not_full = 0
    skipped_incomplete = 0
    flooded_columns = 0
    counts = {
        "flooded_tree_blocks": 0,
        "flooded_rail_blocks": 0,
        "flooded_shore_flora_blocks": 0,
        "sterile_band_ore_blocks": 0,
    }
    observations = {
        # These are not failure counters. They prove whether the deterministic
        # smoke sample actually contains flora relocated to the new Y=128
        # shoreline; a dedicated positive-presence gate can then be added only
        # when the fixed seed gives a stable non-zero sample.
        "shoreline_lily_pad_blocks_y129": 0,
        "shoreline_sugar_cane_blocks_y129_131": 0,
    }
    violations: list[dict] = []

    for cx, cz in TOPO.generated_chunks(region):
        if scanned >= max_chunks:
            break
        records_seen += 1
        try:
            root = BASE.read_chunk_nbt(region, cx, cz)
        except Exception:
            continue
        if not TOPO.is_full_chunk(root):
            skipped_not_full += 1
            continue
        try:
            decoded = TOPO.decoded_sample_sections(root, SCAN_MIN_Y, 143)
        except Exception:
            skipped_incomplete += 1
            continue
        scanned += 1
        base_x = cx * 16
        base_z = cz * 16

        # Positive shoreline observations. The relocation hook writes lily pads
        # at Y=129 and sugar cane starting at Y=129, up to three blocks tall.
        for lz in range(1, 15):
            for lx in range(1, 15):
                if block_at(decoded, 129, lx, lz) == "minecraft:lily_pad" and block_at(decoded, 128, lx, lz) == "minecraft:water":
                    observations["shoreline_lily_pad_blocks_y129"] += 1
                for y in range(129, 132):
                    if block_at(decoded, y, lx, lz) == "minecraft:sugar_cane":
                        observations["shoreline_sugar_cane_blocks_y129_131"] += 1

        # Surface-flood regression checks. Edges are skipped so that deciding
        # whether a block is submerged never requires reading a neighbour chunk.
        for lz in range(1, 15):
            for lx in range(1, 15):
                if block_at(decoded, FLOOD_Y, lx, lz) != "minecraft:water":
                    continue
                flooded_columns += 1
                for y in range(SCAN_MIN_Y, FLOOD_Y + 1):
                    name = block_at(decoded, y, lx, lz)
                    category = None
                    if is_tree_block(name):
                        category = "flooded_tree_blocks"
                    elif name in RAILS:
                        category = "flooded_rail_blocks"
                    elif name in SHORE_FLORA:
                        category = "flooded_shore_flora_blocks"
                    if category is not None:
                        counts[category] += 1
                        if len(violations) < 100:
                            violations.append({
                                "category": category,
                                "block": name,
                                "pos": [base_x + lx, y, base_z + lz],
                                "chunk": [cx, cz],
                            })

        # The field-r1 ore policy intentionally leaves Y=65..135 sterile so
        # vanilla upper/lower ore bands do not appear immediately beneath the
        # artificial Y=128 flood surface.
        for y in range(SCAN_MIN_Y, ORE_MAX_Y + 1):
            for lz in range(16):
                for lx in range(16):
                    name = block_at(decoded, y, lx, lz)
                    if name not in ORES:
                        continue
                    counts["sterile_band_ore_blocks"] += 1
                    if len(violations) < 100:
                        violations.append({
                            "category": "sterile_band_ore_blocks",
                            "block": name,
                            "pos": [base_x + lx, y, base_z + lz],
                            "chunk": [cx, cz],
                        })

    if scanned == 0:
        fail(
            "no complete FULL chunks were available; "
            f"records_seen={records_seen} not_full={skipped_not_full} incomplete={skipped_incomplete}"
        )
    if flooded_columns == 0:
        fail("no Y=128 flooded columns were observed; field surface audit sample is ineffective")

    return {
        "schema": 2,
        "purpose": "lock first-field-test regressions at the Y=128 NeverOverworld flood surface",
        "flood_y": FLOOD_Y,
        "surface_scan_y": [SCAN_MIN_Y, FLOOD_Y],
        "ore_sterile_y": [SCAN_MIN_Y, ORE_MAX_Y],
        "selection": {
            "records_seen": records_seen,
            "chunks_scanned": scanned,
            "skipped_not_full": skipped_not_full,
            "skipped_incomplete": skipped_incomplete,
            "flooded_columns": flooded_columns,
        },
        "counts": counts,
        "observations": observations,
        "violations": violations,
    }


def self_test() -> None:
    positives = {
        "minecraft:oak_log",
        "minecraft:stripped_oak_wood",
        "minecraft:warped_stem",
        "minecraft:crimson_hyphae",
        "minecraft:oak_leaves",
        "minecraft:mangrove_roots",
    }
    for name in positives:
        if not is_tree_block(name):
            fail(f"SELF-TEST failed to classify tree block: {name}")
    for name in ("minecraft:stone", "minecraft:rail", "minecraft:sugar_cane", "minecraft:coal_ore"):
        if is_tree_block(name):
            fail(f"SELF-TEST false tree classification: {name}")
    if "minecraft:deepslate_diamond_ore" not in ORES or "minecraft:powered_rail" not in RAILS:
        fail("SELF-TEST regression block sets are incomplete")
    print("[NeverFolia][NeverOverworld flood surface audit] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit field-test flood-surface regressions in NeverOverworld")
    parser.add_argument("--world", type=Path)
    parser.add_argument("--max-chunks", type=int, default=1024)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-on-violations", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.world is None:
        parser.error("--world is required")

    result = audit(args.world.resolve(), max(1, args.max_chunks))
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")

    if args.fail_on_violations:
        bad = {key: value for key, value in result["counts"].items() if value}
        if bad:
            fail(f"field flood-surface regression gate failed: {bad}")


if __name__ == "__main__":
    main()
