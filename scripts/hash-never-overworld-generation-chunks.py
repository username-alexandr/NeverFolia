#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_HASHER = ROOT / "scripts/hash-never-nether-chunks.py"
BODY_SECTION_MIN = -32
BODY_SECTION_MAX = 31
ALGORITHM = "neveroverworld-generation-semantic-v1"


def load_base_hasher():
    spec = importlib.util.spec_from_file_location("neverworld_raw_hasher", BASE_HASHER)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load base chunk hasher: {BASE_HASHER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = load_base_hasher()


def palette_state(entry) -> str:
    if isinstance(entry, str):
        return entry
    if not isinstance(entry, dict):
        raise ValueError(f"unsupported block-state palette entry: {entry!r}")
    name = entry.get("Name", entry.get("name"))
    if not isinstance(name, str):
        raise ValueError(f"block-state palette entry has no name: {entry!r}")
    props = entry.get("Properties", entry.get("properties", {}))
    if not isinstance(props, dict) or not props:
        return name
    ordered = ",".join(f"{key}={props[key]}" for key in sorted(props))
    return f"{name}[{ordered}]"


def generation_state(entry) -> str:
    if isinstance(entry, dict):
        name = entry.get("Name", entry.get("name"))
        props = entry.get("Properties", entry.get("properties", {}))
        if name in {"minecraft:water", "minecraft:lava"} and isinstance(props, dict):
            level = props.get("level")
            if level is not None and str(level) != "0":
                # Flowing fluid is scheduled-tick simulation after FULL, not a
                # generated source state. Preserve source water/lava strictly.
                return "minecraft:air"
    return palette_state(entry)


def section_semantic_digest(section: dict) -> str:
    states = section.get("block_states", section.get("BlockStates"))
    if not isinstance(states, dict):
        palette = ["minecraft:air"]
        longs: list[int] = []
    else:
        raw_palette = states.get("palette")
        palette = [generation_state(entry) for entry in raw_palette] if isinstance(raw_palette, list) and raw_palette else ["minecraft:air"]
        wrapper = states.get("data")
        longs = wrapper.get("$long_array", []) if isinstance(wrapper, dict) else []

    digest = hashlib.sha256()
    if len(palette) == 1:
        encoded = palette[0].encode("utf-8") + b"\0"
        for _ in range(4096):
            digest.update(encoded)
        return digest.hexdigest()

    bits = max(4, (len(palette) - 1).bit_length())
    per_long = 64 // bits
    mask = (1 << bits) - 1
    for index in range(4096):
        long_index = index // per_long
        bit_offset = (index % per_long) * bits
        if long_index >= len(longs):
            raise ValueError(f"packed block-state data too short in section Y={section.get('Y')}")
        packed = longs[long_index] & 0xFFFFFFFFFFFFFFFF
        palette_index = (packed >> bit_offset) & mask
        if palette_index >= len(palette):
            raise ValueError(f"palette index {palette_index} out of range {len(palette)}")
        digest.update(palette[palette_index].encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def canonical_generation_chunk(root: dict) -> dict:
    sections = []
    for section in BASE.section_list(root):
        y = section.get("Y")
        if not isinstance(y, int) or y < BODY_SECTION_MIN or y > BODY_SECTION_MAX:
            continue
        sections.append({"Y": y, "blocks_semantic_sha256": section_semantic_digest(section), "biomes": section.get("biomes")})
    sections.sort(key=lambda item: item["Y"])
    return {
        "xPos": root.get("xPos"),
        "zPos": root.get("zPos"),
        "yPos": root.get("yPos"),
        "Status": root.get("Status", root.get("status")),
        "sections": sections,
        "Heightmaps": root.get("Heightmaps", root.get("heightmaps", {})),
        "structures": root.get("structures", root.get("Structures", {})),
    }


def canonical_bytes(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def chunk_digest(root: dict) -> str:
    return hashlib.sha256(canonical_bytes(canonical_generation_chunk(root))).hexdigest()


def parse_chunk_arg(value: str) -> tuple[int, int]:
    try:
        x, z = value.split(",", 1)
        return int(x), int(z)
    except Exception as exc:
        raise argparse.ArgumentTypeError(f"chunk must be x,z; got {value!r}") from exc


def build_manifest(world: Path, chunks: list[tuple[int, int]]) -> dict:
    region_dir = BASE.find_region_dir(world)
    entries = []
    for cx, cz in sorted(set(chunks)):
        root = BASE.read_chunk_nbt(region_dir, cx, cz)
        entries.append({"x": cx, "z": cz, "sha256": chunk_digest(root)})
    overall = hashlib.sha256()
    for entry in entries:
        overall.update(f"{entry['x']},{entry['z']}:{entry['sha256']}\n".encode("ascii"))
    return {
        "schema": 1,
        "algorithm": ALGORITHM,
        "normalization": {
            "minecraft:water[level>0]": "minecraft:air",
            "minecraft:lava[level>0]": "minecraft:air",
            "source_fluids_level=0": "preserved",
        },
        "body_section_min": BODY_SECTION_MIN,
        "body_section_max": BODY_SECTION_MAX,
        "chunk_count": len(entries),
        "chunks": entries,
        "overall_sha256": overall.hexdigest(),
    }


def self_test() -> None:
    air = {"Y": 0, "block_states": {"palette": [{"Name": "minecraft:air"}]}, "biomes": {"palette": ["minecraft:plains"]}}
    flowing_water = {"Y": 0, "block_states": {"palette": [{"Name": "minecraft:water", "Properties": {"level": "8"}}]}, "biomes": {"palette": ["minecraft:plains"]}}
    source_water = {"Y": 0, "block_states": {"palette": [{"Name": "minecraft:water", "Properties": {"level": "0"}}]}, "biomes": {"palette": ["minecraft:plains"]}}
    if section_semantic_digest(air) != section_semantic_digest(flowing_water):
        raise SystemExit("flowing water normalization self-test failed")
    if section_semantic_digest(air) == section_semantic_digest(source_water):
        raise SystemExit("source water was incorrectly normalized")
    print("[NeverFolia][NeverOverworld determinism] HASHER SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hash semantic NeverOverworld generation state")
    parser.add_argument("--world", type=Path)
    parser.add_argument("--chunk", action="append", type=parse_chunk_arg, default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.world is None or not args.chunk:
        parser.error("--world and at least one --chunk are required")
    manifest = build_manifest(args.world, args.chunk)
    text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
