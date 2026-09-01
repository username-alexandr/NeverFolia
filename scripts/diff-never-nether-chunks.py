#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HASHER_PATH = ROOT / "scripts" / "hash-never-nether-chunks.py"


def load_hasher():
    spec = importlib.util.spec_from_file_location("nevernether_chunk_hasher", HASHER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load hasher module: {HASHER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HASHER = load_hasher()


def digest(value) -> str:
    return hashlib.sha256(HASHER.canonical_bytes(value)).hexdigest()


def palette_entry_identity(entry) -> str:
    if isinstance(entry, str):
        return entry
    if not isinstance(entry, dict):
        raise ValueError(f"unsupported palette entry: {entry!r}")

    name = entry.get("Name", entry.get("name"))
    if not isinstance(name, str):
        raise ValueError(f"palette entry has no namespaced name: {entry!r}")

    properties = entry.get("Properties", entry.get("properties"))
    if not isinstance(properties, dict) or not properties:
        return name

    encoded = ",".join(f"{key}={properties[key]}" for key in sorted(properties))
    return f"{name}[{encoded}]"


def long_array(value) -> list[int]:
    if not isinstance(value, dict) or "$long_array" not in value:
        raise ValueError("paletted container has no TAG_Long_Array data")
    longs = value["$long_array"]
    if not isinstance(longs, list):
        raise ValueError("paletted container long-array wrapper is malformed")
    return longs


def decode_paletted_container(
    container: dict | None,
    *,
    entry_count: int,
    min_bits: int,
) -> tuple[list[str], int]:
    if not isinstance(container, dict):
        raise ValueError("missing paletted container")
    palette = container.get("palette")
    if not isinstance(palette, list) or not palette:
        raise ValueError("paletted container has no palette")

    identities = [palette_entry_identity(entry) for entry in palette]
    if len(identities) == 1:
        return [identities[0]] * entry_count, 0

    bits = max(min_bits, (len(identities) - 1).bit_length())
    values_per_long = 64 // bits
    if values_per_long <= 0:
        raise ValueError(f"invalid palette bit width: {bits}")

    longs = long_array(container.get("data"))
    required_longs = (entry_count + values_per_long - 1) // values_per_long
    if len(longs) < required_longs:
        raise ValueError(
            f"packed palette data too short: need {required_longs} longs for "
            f"{entry_count} values at {bits} bits, have {len(longs)}"
        )

    mask = (1 << bits) - 1
    decoded: list[str] = []
    for index in range(entry_count):
        packed = longs[index // values_per_long] & 0xFFFFFFFFFFFFFFFF
        bit_offset = (index % values_per_long) * bits
        palette_index = (packed >> bit_offset) & mask
        if palette_index >= len(identities):
            raise ValueError(
                f"palette index {palette_index} out of range {len(identities)} "
                f"at logical index {index}"
            )
        decoded.append(identities[palette_index])
    return decoded, bits


def section_map(root: dict) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for section in HASHER.section_list(root):
        y = section.get("Y")
        if isinstance(y, int):
            out[y] = section
    return out


def section_block_container(section: dict) -> dict | None:
    value = section.get("block_states", section.get("BlockStates"))
    return value if isinstance(value, dict) else None


def section_biome_container(section: dict) -> dict | None:
    value = section.get("biomes")
    return value if isinstance(value, dict) else None


def component_summary(root: dict) -> dict:
    canonical = HASHER.canonical_chunk(root)
    sections = []
    for section in canonical["sections"]:
        sections.append(
            {
                "Y": section["Y"],
                "block_states_sha256": digest(section.get("block_states")),
                "biomes_sha256": digest(section.get("biomes")),
            }
        )
    return {
        "canonical_sha256": digest(canonical),
        "metadata_sha256": digest(
            {
                "xPos": canonical.get("xPos"),
                "zPos": canonical.get("zPos"),
                "yPos": canonical.get("yPos"),
                "Status": canonical.get("Status"),
            }
        ),
        "heightmaps_sha256": digest(canonical.get("Heightmaps", {})),
        "structures_sha256": digest(canonical.get("structures", {})),
        "sections_sha256": digest(canonical.get("sections", [])),
        "sections": sections,
    }


def compare_components(a: dict, b: dict) -> dict:
    fields = (
        "metadata_sha256",
        "heightmaps_sha256",
        "structures_sha256",
        "sections_sha256",
    )
    changed_components = [field for field in fields if a[field] != b[field]]

    sections_a = {item["Y"]: item for item in a["sections"]}
    sections_b = {item["Y"]: item for item in b["sections"]}
    section_differences = []
    for y in sorted(set(sections_a) | set(sections_b)):
        left = sections_a.get(y)
        right = sections_b.get(y)
        if left == right:
            continue
        entry = {"Y": y, "present_a": left is not None, "present_b": right is not None}
        if left is not None and right is not None:
            entry["block_states_changed"] = (
                left["block_states_sha256"] != right["block_states_sha256"]
            )
            entry["biomes_changed"] = left["biomes_sha256"] != right["biomes_sha256"]
            entry["a"] = left
            entry["b"] = right
        section_differences.append(entry)

    return {
        "changed_components": changed_components,
        "section_differences": section_differences,
    }


def semantic_block_diff(
    root_a: dict,
    root_b: dict,
    *,
    chunk_x: int,
    chunk_z: int,
    changed_sections: list[dict],
) -> dict:
    sections_a = section_map(root_a)
    sections_b = section_map(root_b)
    details = []
    total_differences = 0
    semantic_changed_sections: list[int] = []
    encoding_only_sections: list[int] = []

    for raw_diff in changed_sections:
        if not raw_diff.get("block_states_changed"):
            continue
        y = raw_diff["Y"]
        section_a = sections_a.get(y)
        section_b = sections_b.get(y)
        if section_a is None or section_b is None:
            continue

        blocks_a, bits_a = decode_paletted_container(
            section_block_container(section_a), entry_count=4096, min_bits=4
        )
        blocks_b, bits_b = decode_paletted_container(
            section_block_container(section_b), entry_count=4096, min_bits=4
        )
        semantic_a = digest(blocks_a)
        semantic_b = digest(blocks_b)
        different_indices = [
            index for index, (left, right) in enumerate(zip(blocks_a, blocks_b)) if left != right
        ]
        difference_count = len(different_indices)
        total_differences += difference_count

        if difference_count:
            semantic_changed_sections.append(y)
        else:
            encoding_only_sections.append(y)

        samples = []
        for index in different_indices[:6]:
            local_y = index >> 8
            local_z = (index >> 4) & 15
            local_x = index & 15
            samples.append(
                {
                    "x": chunk_x * 16 + local_x,
                    "y": y * 16 + local_y,
                    "z": chunk_z * 16 + local_z,
                    "a": blocks_a[index],
                    "b": blocks_b[index],
                }
            )

        container_a = section_block_container(section_a) or {}
        container_b = section_block_container(section_b) or {}
        palette_a = container_a.get("palette", [])
        palette_b = container_b.get("palette", [])
        details.append(
            {
                "Y": y,
                "semantic_same": difference_count == 0,
                "semantic_sha256_a": semantic_a,
                "semantic_sha256_b": semantic_b,
                "different_block_count": difference_count,
                "storage_bits_a": bits_a,
                "storage_bits_b": bits_b,
                "palette_size_a": len(palette_a) if isinstance(palette_a, list) else None,
                "palette_size_b": len(palette_b) if isinstance(palette_b, list) else None,
                "samples": samples,
            }
        )

    return {
        "semantic_block_difference_count": total_differences,
        "semantic_changed_sections": semantic_changed_sections,
        "encoding_only_sections": encoding_only_sections,
        "semantic_section_details": details,
    }


def build_report(world_a: Path, world_b: Path, chunks: list[tuple[int, int]]) -> dict:
    region_a = HASHER.find_region_dir(world_a)
    region_b = HASHER.find_region_dir(world_b)
    compared = []
    mismatches = []

    for cx, cz in sorted(set(chunks)):
        root_a = HASHER.read_chunk_nbt(region_a, cx, cz)
        root_b = HASHER.read_chunk_nbt(region_b, cx, cz)
        summary_a = component_summary(root_a)
        summary_b = component_summary(root_b)
        same = summary_a["canonical_sha256"] == summary_b["canonical_sha256"]
        item = {
            "x": cx,
            "z": cz,
            "same": same,
            "a": summary_a,
            "b": summary_b,
        }
        if not same:
            component_diff = compare_components(summary_a, summary_b)
            item.update(component_diff)
            item.update(
                semantic_block_diff(
                    root_a,
                    root_b,
                    chunk_x=cx,
                    chunk_z=cz,
                    changed_sections=component_diff["section_differences"],
                )
            )
            mismatches.append(item)
        compared.append(item)

    return {
        "schema": 2,
        "algorithm": HASHER.ALGORITHM,
        "world_a": str(world_a),
        "world_b": str(world_b),
        "chunk_count": len(compared),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }


def print_report(report: dict) -> None:
    print("[NeverFolia][NeverNether determinism] COMPONENT DIFF")
    print("  chunks:", report["chunk_count"])
    print("  mismatches:", report["mismatch_count"])
    for item in report["mismatches"]:
        print(f"  chunk {item['x']},{item['z']}:")
        print("    components:", ", ".join(item["changed_components"]) or "none")
        print("    semantic block differences:", item["semantic_block_difference_count"])
        if item["encoding_only_sections"]:
            print("    encoding-only sections:", ", ".join(map(str, item["encoding_only_sections"])))
        if item["semantic_changed_sections"]:
            print("    semantic changed sections:", ", ".join(map(str, item["semantic_changed_sections"])))
        for detail in item["semantic_section_details"]:
            print(
                f"    section Y={detail['Y']}: semantic_same={detail['semantic_same']} "
                f"different_blocks={detail['different_block_count']} "
                f"palette={detail['palette_size_a']}/{detail['palette_size_b']} "
                f"bits={detail['storage_bits_a']}/{detail['storage_bits_b']}"
            )
            for sample in detail["samples"]:
                print(
                    f"      {sample['x']},{sample['y']},{sample['z']}: "
                    f"{sample['a']} != {sample['b']}"
                )


def pack_indices(indices: list[int], bits: int) -> list[int]:
    values_per_long = 64 // bits
    longs = [0] * ((len(indices) + values_per_long - 1) // values_per_long)
    mask = (1 << bits) - 1
    for index, value in enumerate(indices):
        longs[index // values_per_long] |= (value & mask) << ((index % values_per_long) * bits)
    return longs


def self_test() -> None:
    a = {
        "canonical_sha256": "a",
        "metadata_sha256": "m",
        "heightmaps_sha256": "h1",
        "structures_sha256": "s",
        "sections_sha256": "x1",
        "sections": [
            {"Y": 0, "block_states_sha256": "b1", "biomes_sha256": "q"},
            {"Y": 1, "block_states_sha256": "b2", "biomes_sha256": "q"},
        ],
    }
    b = {
        "canonical_sha256": "b",
        "metadata_sha256": "m",
        "heightmaps_sha256": "h2",
        "structures_sha256": "s",
        "sections_sha256": "x2",
        "sections": [
            {"Y": 0, "block_states_sha256": "c1", "biomes_sha256": "q"},
            {"Y": 1, "block_states_sha256": "b2", "biomes_sha256": "q"},
        ],
    }
    diff = compare_components(a, b)
    if diff["changed_components"] != ["heightmaps_sha256", "sections_sha256"]:
        raise SystemExit(f"component diff self-test failed: {diff!r}")
    if len(diff["section_differences"]) != 1:
        raise SystemExit(f"section diff self-test failed: {diff!r}")
    if not diff["section_differences"][0]["block_states_changed"]:
        raise SystemExit(f"block-state diff self-test failed: {diff!r}")

    semantic = [0] * 4096
    semantic[3] = 1
    container_a = {
        "palette": [
            {"Name": "minecraft:air"},
            {"Name": "minecraft:stone"},
        ],
        "data": {"$long_array": pack_indices(semantic, 4)},
    }
    reversed_indices = [1 if value == 0 else 0 for value in semantic]
    container_b = {
        "palette": [
            {"Name": "minecraft:stone"},
            {"Name": "minecraft:air"},
        ],
        "data": {"$long_array": pack_indices(reversed_indices, 4)},
    }
    decoded_a, _ = decode_paletted_container(container_a, entry_count=4096, min_bits=4)
    decoded_b, _ = decode_paletted_container(container_b, entry_count=4096, min_bits=4)
    if decoded_a != decoded_b:
        raise SystemExit("semantic palette normalization self-test failed")
    if digest(container_a) == digest(container_b):
        raise SystemExit("raw palette self-test did not create distinct encodings")

    mutated = list(semantic)
    mutated[5] = 1
    container_c = {
        "palette": container_a["palette"],
        "data": {"$long_array": pack_indices(mutated, 4)},
    }
    decoded_c, _ = decode_paletted_container(container_c, entry_count=4096, min_bits=4)
    if decoded_a == decoded_c:
        raise SystemExit("semantic block mutation self-test failed")

    print("[NeverFolia][NeverNether determinism] COMPONENT DIFF SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose canonical NeverNether chunk differences between two worlds"
    )
    parser.add_argument("--world-a", type=Path)
    parser.add_argument("--world-b", type=Path)
    parser.add_argument("--chunk", action="append", type=HASHER.parse_chunk_arg, default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-differences", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.world_a is None or args.world_b is None:
        parser.error("--world-a and --world-b are required")
    if not args.chunk:
        parser.error("at least one --chunk is required")

    report = build_report(args.world_a, args.world_b, args.chunk)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print_report(report)

    if report["mismatch_count"] and not args.allow_differences:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
