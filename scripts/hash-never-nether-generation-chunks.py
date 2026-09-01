#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_HASHER = ROOT / "scripts/hash-never-nether-chunks.py"
BODY_SECTION_MIN = -8
BODY_SECTION_MAX = 23
ALGORITHM = "nevernether-generation-semantic-v1"


def load_base_hasher():
    spec = importlib.util.spec_from_file_location("nevernether_raw_hasher", BASE_HASHER)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Cannot load base NeverNether hasher: {BASE_HASHER}")
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
    properties = entry.get("Properties", entry.get("properties", {}))
    if not isinstance(properties, dict) or not properties:
        return name
    ordered = ",".join(f"{key}={properties[key]}" for key in sorted(properties))
    return f"{name}[{ordered}]"


def generation_state(entry) -> str:
    """Normalize only post-FULL fluid evolution, never generated source lava."""
    if isinstance(entry, dict):
        name = entry.get("Name", entry.get("name"))
        properties = entry.get("Properties", entry.get("properties", {}))
        if name == "minecraft:lava" and isinstance(properties, dict):
            level = properties.get("level")
            if level is not None and str(level) != "0":
                # Non-source lava is created by scheduled fluid ticks after the
                # chunk reaches FULL. It is runtime simulation state, not a
                # worldgen output. Treat it as the air cell it flowed into.
                return "minecraft:air"
    return palette_state(entry)


def section_semantic_digest(section: dict) -> str:
    states = section.get("block_states", section.get("BlockStates"))
    if not isinstance(states, dict):
        palette = ["minecraft:air"]
        longs: list[int] = []
    else:
        raw_palette = states.get("palette")
        if not isinstance(raw_palette, list) or not raw_palette:
            palette = ["minecraft:air"]
        else:
            palette = [generation_state(entry) for entry in raw_palette]
        data_wrapper = states.get("data")
        if isinstance(data_wrapper, dict) and "$long_array" in data_wrapper:
            longs = data_wrapper["$long_array"]
        else:
            longs = []

    digest = hashlib.sha256()
    if len(palette) == 1:
        encoded = palette[0].encode("utf-8") + b"\0"
        for _ in range(4096):
            digest.update(encoded)
        return digest.hexdigest()

    bits = max(4, (len(palette) - 1).bit_length())
    values_per_long = 64 // bits
    mask = (1 << bits) - 1
    for index in range(4096):
        long_index = index // values_per_long
        bit_offset = (index % values_per_long) * bits
        if long_index >= len(longs):
            raise ValueError(
                f"packed block-state data too short in section Y={section.get('Y')}: "
                f"need long {long_index}, have {len(longs)}"
            )
        packed = longs[long_index] & 0xFFFFFFFFFFFFFFFF
        palette_index = (packed >> bit_offset) & mask
        if palette_index >= len(palette):
            raise ValueError(
                f"palette index {palette_index} out of range {len(palette)} "
                f"in section Y={section.get('Y')}"
            )
        digest.update(palette[palette_index].encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def canonical_generation_chunk(root: dict) -> dict:
    sections = []
    for section in BASE.section_list(root):
        y = section.get("Y")
        if not isinstance(y, int) or y < BODY_SECTION_MIN or y > BODY_SECTION_MAX:
            continue
        sections.append(
            {
                "Y": y,
                "blocks_semantic_sha256": section_semantic_digest(section),
                "biomes": section.get("biomes"),
            }
        )
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
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def chunk_digest(root: dict) -> str:
    return hashlib.sha256(canonical_bytes(canonical_generation_chunk(root))).hexdigest()


def parse_chunk_arg(value: str) -> tuple[int, int]:
    try:
        x_text, z_text = value.split(",", 1)
        return int(x_text), int(z_text)
    except Exception as exc:
        raise argparse.ArgumentTypeError(
            f"chunk must be formatted as x,z; got {value!r}"
        ) from exc


def build_manifest(world: Path, chunks: list[tuple[int, int]]) -> dict:
    region_dir = BASE.find_region_dir(world)
    entries = []
    for cx, cz in sorted(set(chunks)):
        root = BASE.read_chunk_nbt(region_dir, cx, cz)
        if root.get("xPos") != cx or root.get("zPos") != cz:
            raise ValueError(
                f"chunk coordinate mismatch: requested {cx},{cz}, "
                f"NBT has {root.get('xPos')},{root.get('zPos')}"
            )
        entries.append({"x": cx, "z": cz, "sha256": chunk_digest(root)})

    overall = hashlib.sha256()
    for entry in entries:
        overall.update(
            f"{entry['x']},{entry['z']}:{entry['sha256']}\n".encode("ascii")
        )
    return {
        "schema": 1,
        "algorithm": ALGORITHM,
        "normalization": {
            "minecraft:lava[level>0]": "minecraft:air",
            "minecraft:lava[level=0]": "preserved",
        },
        "body_section_min": BODY_SECTION_MIN,
        "body_section_max": BODY_SECTION_MAX,
        "chunk_count": len(entries),
        "chunks": entries,
        "overall_sha256": overall.hexdigest(),
    }


def self_test() -> None:
    air = {
        "Y": 0,
        "block_states": {"palette": [{"Name": "minecraft:air"}]},
        "biomes": {"palette": ["minecraft:nether_wastes"]},
    }
    flowing = {
        "Y": 0,
        "block_states": {
            "palette": [
                {"Name": "minecraft:lava", "Properties": {"level": "8"}}
            ]
        },
        "biomes": {"palette": ["minecraft:nether_wastes"]},
    }
    source = {
        "Y": 0,
        "block_states": {
            "palette": [
                {"Name": "minecraft:lava", "Properties": {"level": "0"}}
            ]
        },
        "biomes": {"palette": ["minecraft:nether_wastes"]},
    }
    if section_semantic_digest(air) != section_semantic_digest(flowing):
        raise SystemExit("flowing lava normalization self-test failed")
    if section_semantic_digest(air) == section_semantic_digest(source):
        raise SystemExit("source lava was incorrectly normalized away")

    root_air = {
        "xPos": 0,
        "zPos": 0,
        "yPos": -8,
        "Status": "minecraft:full",
        "sections": [air],
        "Heightmaps": {},
        "structures": {},
    }
    root_flowing = dict(root_air)
    root_flowing["sections"] = [flowing]
    root_source = dict(root_air)
    root_source["sections"] = [source]
    if chunk_digest(root_air) != chunk_digest(root_flowing):
        raise SystemExit("chunk digest still depends on post-FULL flowing lava")
    if chunk_digest(root_air) == chunk_digest(root_source):
        raise SystemExit("chunk digest failed to preserve generated source lava")
    print("[NeverFolia][NeverNether generation determinism] HASHER SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Hash semantic NeverNether generation state from saved chunks"
    )
    parser.add_argument("--world", type=Path)
    parser.add_argument("--chunk", action="append", type=parse_chunk_arg, default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.world is None:
        parser.error("--world is required")
    if not args.chunk:
        parser.error("at least one --chunk is required")

    manifest = build_manifest(args.world, args.chunk)
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)


if __name__ == "__main__":
    main()
