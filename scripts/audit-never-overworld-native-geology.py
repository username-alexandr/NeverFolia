#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HASHER = ROOT / "scripts/hash-never-overworld-generation-chunks.py"

spec = importlib.util.spec_from_file_location("nr_hasher", HASHER)
if spec is None or spec.loader is None:
    raise SystemExit(f"cannot import NeverOverworld hasher: {HASHER}")
NR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(NR)
BASE = NR.BASE

DEEP_SECTION_MIN = -32
DEEP_SECTION_MAX = -7
ORE_NAMES = {
    "minecraft:coal_ore": "coal",
    "minecraft:deepslate_coal_ore": "coal",
    "minecraft:iron_ore": "iron",
    "minecraft:deepslate_iron_ore": "iron",
    "minecraft:copper_ore": "copper",
    "minecraft:deepslate_copper_ore": "copper",
    "minecraft:gold_ore": "gold",
    "minecraft:deepslate_gold_ore": "gold",
    "minecraft:redstone_ore": "redstone",
    "minecraft:deepslate_redstone_ore": "redstone",
    "minecraft:lapis_ore": "lapis",
    "minecraft:deepslate_lapis_ore": "lapis",
    "minecraft:diamond_ore": "diamond",
    "minecraft:deepslate_diamond_ore": "diamond",
    "minecraft:emerald_ore": "emerald",
    "minecraft:deepslate_emerald_ore": "emerald",
}
REGION_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld geology audit] {message}")


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


def palette_name(entry) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        value = entry.get("Name", entry.get("name"))
        if isinstance(value, str):
            return value
    raise ValueError(f"invalid palette entry: {entry!r}")


def count_section(section: dict, counts: Counter[str]) -> int:
    states = section.get("block_states", section.get("BlockStates"))
    if not isinstance(states, dict):
        return 0
    raw_palette = states.get("palette")
    if not isinstance(raw_palette, list) or not raw_palette:
        return 0
    palette = [palette_name(entry) for entry in raw_palette]
    if len(palette) == 1:
        kind = ORE_NAMES.get(palette[0])
        if kind is not None:
            counts[kind] += 4096
            return 4096
        return 0

    wrapper = states.get("data")
    longs = wrapper.get("$long_array", []) if isinstance(wrapper, dict) else []
    bits = max(4, (len(palette) - 1).bit_length())
    per_long = 64 // bits
    mask = (1 << bits) - 1
    total = 0
    for index in range(4096):
        li = index // per_long
        if li >= len(longs):
            fail(f"packed block-state data too short in section Y={section.get('Y')}")
        shift = (index % per_long) * bits
        pi = ((longs[li] & 0xFFFFFFFFFFFFFFFF) >> shift) & mask
        if pi >= len(palette):
            fail(f"palette index {pi} out of range {len(palette)}")
        kind = ORE_NAMES.get(palette[pi])
        if kind is not None:
            counts[kind] += 1
            total += 1
    return total


def audit(world: Path, max_chunks: int) -> dict:
    region = NR.find_region_dir(world)
    counts: Counter[str] = Counter()
    chunks_scanned = 0
    deep_sections = 0
    chunks_with_ore = 0
    for cx, cz in generated_chunks(region):
        if chunks_scanned >= max_chunks:
            break
        try:
            root = BASE.read_chunk_nbt(region, cx, cz)
        except Exception:
            continue
        chunks_scanned += 1
        before = sum(counts.values())
        for section in BASE.section_list(root):
            sy = section.get("Y")
            if not isinstance(sy, int) or sy < DEEP_SECTION_MIN or sy > DEEP_SECTION_MAX:
                continue
            deep_sections += 1
            count_section(section, counts)
        if sum(counts.values()) > before:
            chunks_with_ore += 1

    total = sum(counts.values())
    result = {
        "schema": 1,
        "deep_y": [-512, -97],
        "chunks_scanned": chunks_scanned,
        "deep_sections_scanned": deep_sections,
        "chunks_with_native_ore": chunks_with_ore,
        "total_deep_ore_blocks": total,
        "ore_blocks": {kind: counts.get(kind, 0) for kind in ("coal", "iron", "copper", "gold", "redstone", "lapis", "diamond", "emerald")},
    }
    if chunks_scanned == 0 or deep_sections == 0:
        fail("no generated deep NeverOverworld chunk sections were available for audit")
    if total == 0:
        fail("no ore blocks found below Y=-96 after native geology promotion")
    if counts.get("iron", 0) == 0:
        fail("native deep audit found no iron; expected common province veins in generated sample")
    return result


def self_test() -> None:
    counts: Counter[str] = Counter()
    section = {"Y": -10, "block_states": {"palette": [{"Name": "minecraft:deepslate_iron_ore"}]}}
    if count_section(section, counts) != 4096 or counts["iron"] != 4096:
        fail("SELF-TEST: single-palette ore counting failed")
    empty = Counter()
    section2 = {"Y": -10, "block_states": {"palette": [{"Name": "minecraft:deepslate"}]}}
    if count_section(section2, empty) != 0:
        fail("SELF-TEST: host rock was counted as ore")
    print("[NeverFolia][NeverOverworld geology audit] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit deep NR-DEV-1 NBT for native geology ore output")
    parser.add_argument("--world", type=Path)
    parser.add_argument("--max-chunks", type=int, default=256)
    parser.add_argument("--output", type=Path)
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


if __name__ == "__main__":
    main()
