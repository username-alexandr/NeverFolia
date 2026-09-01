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
            item.update(compare_components(summary_a, summary_b))
            mismatches.append(item)
        compared.append(item)

    return {
        "schema": 1,
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
        for section in item["section_differences"]:
            if not section["present_a"] or not section["present_b"]:
                print(
                    f"    section Y={section['Y']}: present_a={section['present_a']} "
                    f"present_b={section['present_b']}"
                )
                continue
            changed = []
            if section.get("block_states_changed"):
                changed.append("block_states")
            if section.get("biomes_changed"):
                changed.append("biomes")
            print(f"    section Y={section['Y']}: {', '.join(changed) or 'hash-only'}")


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
