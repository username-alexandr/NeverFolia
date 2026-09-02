#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HASHER_PATH = ROOT / "scripts" / "hash-never-overworld-generation-chunks.py"


def load_hasher():
    spec = importlib.util.spec_from_file_location("neveroverworld_generation_hasher", HASHER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load NeverOverworld hasher: {HASHER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OW = load_hasher()
BASE = OW.BASE


def digest(value) -> str:
    return hashlib.sha256(OW.canonical_bytes(value)).hexdigest()


def parse_chunk(value: str) -> tuple[int, int]:
    try:
        x, z = value.split(",", 1)
        return int(x), int(z)
    except Exception as exc:
        raise argparse.ArgumentTypeError(f"chunk must be x,z; got {value!r}") from exc


def long_array(value) -> list[int]:
    if not isinstance(value, dict):
        return []
    data = value.get("$long_array", [])
    if not isinstance(data, list):
        raise ValueError("TAG_Long_Array wrapper is malformed")
    return data


def block_container(section: dict) -> dict | None:
    value = section.get("block_states", section.get("BlockStates"))
    return value if isinstance(value, dict) else None


def biome_container(section: dict) -> dict | None:
    value = section.get("biomes")
    return value if isinstance(value, dict) else None


def decode_blocks(section: dict) -> list[str]:
    states = block_container(section)
    if not isinstance(states, dict):
        return ["minecraft:air"] * 4096
    palette_raw = states.get("palette")
    if not isinstance(palette_raw, list) or not palette_raw:
        return ["minecraft:air"] * 4096
    palette = [OW.generation_state(entry) for entry in palette_raw]
    if len(palette) == 1:
        return [palette[0]] * 4096

    bits = max(4, (len(palette) - 1).bit_length())
    per_long = 64 // bits
    mask = (1 << bits) - 1
    longs = long_array(states.get("data"))
    required = (4096 + per_long - 1) // per_long
    if len(longs) < required:
        raise ValueError(f"packed block-state data too short: need {required}, have {len(longs)}")

    out: list[str] = []
    for index in range(4096):
        packed = longs[index // per_long] & 0xFFFFFFFFFFFFFFFF
        palette_index = (packed >> ((index % per_long) * bits)) & mask
        if palette_index >= len(palette):
            raise ValueError(f"palette index {palette_index} out of range {len(palette)}")
        out.append(palette[palette_index])
    return out


def section_map(root: dict) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for section in BASE.section_list(root):
        y = section.get("Y")
        if isinstance(y, int) and OW.BODY_SECTION_MIN <= y <= OW.BODY_SECTION_MAX:
            out[y] = section
    return out


def canonical_component_summary(root: dict) -> dict:
    canonical = OW.canonical_generation_chunk(root)
    section_entries = canonical.get("sections", [])
    return {
        "canonical_sha256": digest(canonical),
        "metadata_sha256": digest({
            "xPos": canonical.get("xPos"),
            "zPos": canonical.get("zPos"),
            "yPos": canonical.get("yPos"),
            "Status": canonical.get("Status"),
        }),
        "heightmaps_sha256": digest(canonical.get("Heightmaps", {})),
        "structures_sha256": digest(canonical.get("structures", {})),
        "sections_sha256": digest(section_entries),
        "sections": {
            int(entry["Y"]): {
                "blocks_semantic_sha256": entry.get("blocks_semantic_sha256"),
                "biomes_sha256": digest(entry.get("biomes")),
            }
            for entry in section_entries
            if isinstance(entry, dict) and isinstance(entry.get("Y"), int)
        },
    }


def changed_components(a: dict, b: dict) -> list[str]:
    fields = ("metadata_sha256", "heightmaps_sha256", "structures_sha256", "sections_sha256")
    return [field for field in fields if a.get(field) != b.get(field)]


def block_diff(root_a: dict, root_b: dict, cx: int, cz: int) -> dict:
    map_a = section_map(root_a)
    map_b = section_map(root_b)
    changed_sections: list[dict] = []
    total = 0
    transition_counts: Counter[str] = Counter()

    for sy in sorted(set(map_a) | set(map_b)):
        section_a = map_a.get(sy)
        section_b = map_b.get(sy)
        if section_a is None or section_b is None:
            changed_sections.append({
                "Y": sy,
                "present_a": section_a is not None,
                "present_b": section_b is not None,
                "different_block_count": None,
                "samples": [],
            })
            continue

        blocks_a = decode_blocks(section_a)
        blocks_b = decode_blocks(section_b)
        indices = [i for i, pair in enumerate(zip(blocks_a, blocks_b)) if pair[0] != pair[1]]
        if not indices:
            continue

        total += len(indices)
        samples = []
        local_counts: Counter[str] = Counter()
        for index in indices:
            left = blocks_a[index]
            right = blocks_b[index]
            key = f"{left} -> {right}"
            local_counts[key] += 1
            transition_counts[key] += 1
        for index in indices[:24]:
            local_y = index >> 8
            local_z = (index >> 4) & 15
            local_x = index & 15
            samples.append({
                "x": cx * 16 + local_x,
                "y": sy * 16 + local_y,
                "z": cz * 16 + local_z,
                "a": blocks_a[index],
                "b": blocks_b[index],
            })
        changed_sections.append({
            "Y": sy,
            "different_block_count": len(indices),
            "transitions": dict(local_counts.most_common()),
            "samples": samples,
        })

    return {
        "semantic_block_difference_count": total,
        "transition_counts": dict(transition_counts.most_common()),
        "changed_block_sections": changed_sections,
    }


def biome_diff(root_a: dict, root_b: dict) -> list[dict]:
    map_a = section_map(root_a)
    map_b = section_map(root_b)
    out = []
    for sy in sorted(set(map_a) | set(map_b)):
        left = biome_container(map_a.get(sy, {}))
        right = biome_container(map_b.get(sy, {}))
        left_hash = digest(left)
        right_hash = digest(right)
        if left_hash != right_hash:
            out.append({"Y": sy, "a_sha256": left_hash, "b_sha256": right_hash})
    return out


def build_report(world_a: Path, world_b: Path, chunks: list[tuple[int, int]]) -> dict:
    region_a = OW.find_region_dir(world_a)
    region_b = OW.find_region_dir(world_b)
    mismatches = []

    for cx, cz in sorted(set(chunks)):
        root_a = BASE.read_chunk_nbt(region_a, cx, cz)
        root_b = BASE.read_chunk_nbt(region_b, cx, cz)
        summary_a = canonical_component_summary(root_a)
        summary_b = canonical_component_summary(root_b)
        if summary_a["canonical_sha256"] == summary_b["canonical_sha256"]:
            continue

        section_keys = sorted(set(summary_a["sections"]) | set(summary_b["sections"]))
        section_hash_diffs = []
        for sy in section_keys:
            left = summary_a["sections"].get(sy)
            right = summary_b["sections"].get(sy)
            if left != right:
                section_hash_diffs.append({"Y": sy, "a": left, "b": right})

        item = {
            "x": cx,
            "z": cz,
            "a_sha256": summary_a["canonical_sha256"],
            "b_sha256": summary_b["canonical_sha256"],
            "changed_components": changed_components(summary_a, summary_b),
            "section_hash_differences": section_hash_diffs,
            "biome_differences": biome_diff(root_a, root_b),
        }
        item.update(block_diff(root_a, root_b, cx, cz))
        mismatches.append(item)

    return {
        "schema": 1,
        "algorithm": OW.ALGORITHM,
        "world_a": str(world_a),
        "world_b": str(world_b),
        "chunk_count": len(set(chunks)),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def print_report(report: dict) -> None:
    print("[NeverFolia][NeverOverworld determinism] COMPONENT DIFF")
    print("  chunks:", report["chunk_count"])
    print("  mismatches:", report["mismatch_count"])
    for item in report["mismatches"]:
        print(f"  chunk {item['x']},{item['z']}:")
        print("    components:", ", ".join(item["changed_components"]) or "none")
        print("    semantic block differences:", item["semantic_block_difference_count"])
        if item["biome_differences"]:
            print("    biome sections:", ", ".join(str(x["Y"]) for x in item["biome_differences"]))
        for transition, count in list(item["transition_counts"].items())[:12]:
            print(f"    {count}x {transition}")
        for section in item["changed_block_sections"]:
            if not section.get("different_block_count"):
                continue
            print(f"    section Y={section['Y']}: {section['different_block_count']} block(s)")
            for sample in section["samples"][:8]:
                print(f"      {sample['x']},{sample['y']},{sample['z']}: {sample['a']} != {sample['b']}")


def pack_indices(indices: list[int], bits: int) -> list[int]:
    per_long = 64 // bits
    longs = [0] * ((len(indices) + per_long - 1) // per_long)
    mask = (1 << bits) - 1
    for index, value in enumerate(indices):
        longs[index // per_long] |= (value & mask) << ((index % per_long) * bits)
    return longs


def self_test() -> None:
    indices = [0] * 4096
    indices[17] = 1
    section = {
        "Y": 0,
        "block_states": {
            "palette": [
                {"Name": "minecraft:air"},
                {"Name": "minecraft:stone"},
            ],
            "data": {"$long_array": pack_indices(indices, 4)},
        },
    }
    decoded = decode_blocks(section)
    if decoded[17] != "minecraft:stone" or decoded[18] != "minecraft:air":
        raise SystemExit("NeverOverworld component diff block decoder self-test failed")

    flowing = {
        "Y": 0,
        "block_states": {"palette": [{"Name": "minecraft:water", "Properties": {"level": "8"}}]},
    }
    if set(decode_blocks(flowing)) != {"minecraft:air"}:
        raise SystemExit("NeverOverworld component diff flowing-fluid normalization self-test failed")
    print("[NeverFolia][NeverOverworld determinism] COMPONENT DIFF SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diff semantic NeverOverworld generation chunks")
    parser.add_argument("--world-a", type=Path)
    parser.add_argument("--world-b", type=Path)
    parser.add_argument("--chunk", action="append", type=parse_chunk, default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-differences", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.world_a is None or args.world_b is None or not args.chunk:
        parser.error("--world-a, --world-b and at least one --chunk are required")

    report = build_report(args.world_a, args.world_b, args.chunk)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print_report(report)
    if report["mismatch_count"] and not args.allow_differences:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
