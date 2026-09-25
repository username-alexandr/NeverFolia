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
ORE_KINDS = ("coal", "iron", "copper", "gold", "redstone", "lapis", "diamond", "emerald")
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
CHUNK_RE = re.compile(r"^(-?\d+),(-?\d+)$")
PROBE_MANIFEST = "geology-priority-chunks.txt"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld geology audit] {message}")


def parse_chunk(value: str) -> tuple[int, int]:
    match = CHUNK_RE.match(value.strip())
    if match is None:
        raise argparse.ArgumentTypeError("chunk must use CX,CZ, for example 31,0 or -17,-25")
    return int(match.group(1)), int(match.group(2))


def load_probe_manifest(world: Path) -> tuple[tuple[tuple[int, int], ...], Path | None]:
    path = world.parent / PROBE_MANIFEST
    if not path.is_file():
        return (), None
    chunks: list[tuple[int, int]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        try:
            chunks.append(parse_chunk(value))
        except argparse.ArgumentTypeError as exc:
            fail(f"invalid {PROBE_MANIFEST} line {line_number}: {exc}")
    if not chunks:
        fail(f"{PROBE_MANIFEST} exists but contains no chunk coordinates")
    return tuple(dict.fromkeys(chunks)), path


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


def record_ore(block_name: str, counts: Counter[str], block_counts: Counter[str], amount: int = 1) -> int:
    kind = ORE_NAMES.get(block_name)
    if kind is None:
        return 0
    counts[kind] += amount
    block_counts[block_name] += amount
    return amount


def count_section(section: dict, counts: Counter[str], block_counts: Counter[str] | None = None) -> int:
    if block_counts is None:
        block_counts = Counter()
    states = section.get("block_states", section.get("BlockStates"))
    if not isinstance(states, dict):
        return 0
    raw_palette = states.get("palette")
    if not isinstance(raw_palette, list) or not raw_palette:
        return 0
    palette = [palette_name(entry) for entry in raw_palette]
    if len(palette) == 1:
        return record_ore(palette[0], counts, block_counts, 4096)

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
        total += record_ore(palette[pi], counts, block_counts)
    return total


def missing_required(result: dict, required_ores: tuple[str, ...], required_blocks: tuple[str, ...]) -> tuple[list[str], list[str]]:
    ore_counts = result.get("ore_blocks", {})
    block_counts = result.get("ore_block_variants", {})
    missing_ores = [kind for kind in required_ores if int(ore_counts.get(kind, 0)) <= 0]
    missing_blocks = [block for block in required_blocks if int(block_counts.get(block, 0)) <= 0]
    return missing_ores, missing_blocks


def audit(world: Path, max_chunks: int, priority_chunks: tuple[tuple[int, int], ...] = ()) -> dict:
    region = NR.find_region_dir(world)
    counts: Counter[str] = Counter()
    block_counts: Counter[str] = Counter()
    chunks_scanned = 0
    deep_sections = 0
    chunks_with_ore = 0
    chunks_with_diamond = 0
    chunks_with_emerald = 0
    chunks_with_gold = 0
    seen: set[tuple[int, int]] = set()
    priority_scanned: list[tuple[int, int]] = []

    def scan_chunk(cx: int, cz: int, root: dict) -> None:
        nonlocal chunks_scanned, deep_sections, chunks_with_ore, chunks_with_diamond, chunks_with_emerald, chunks_with_gold
        chunks_scanned += 1
        before = sum(counts.values())
        diamond_before = counts.get("diamond", 0)
        emerald_before = counts.get("emerald", 0)
        gold_before = counts.get("gold", 0)
        for section in BASE.section_list(root):
            sy = section.get("Y")
            if not isinstance(sy, int) or sy < DEEP_SECTION_MIN or sy > DEEP_SECTION_MAX:
                continue
            deep_sections += 1
            count_section(section, counts, block_counts)
        if sum(counts.values()) > before:
            chunks_with_ore += 1
        if counts.get("diamond", 0) > diamond_before:
            chunks_with_diamond += 1
        if counts.get("emerald", 0) > emerald_before:
            chunks_with_emerald += 1
        if counts.get("gold", 0) > gold_before:
            chunks_with_gold += 1

    # Deterministic rare-ore probes are authoritative CI fixtures. Scan them first
    # so region-file lexical ordering or the general max-chunk cap cannot exclude
    # the exact chunks that the runtime smoke explicitly force-loaded.
    for cx, cz in priority_chunks:
        key = (cx, cz)
        if key in seen:
            continue
        try:
            root = BASE.read_chunk_nbt(region, cx, cz)
        except Exception as exc:
            fail(f"priority chunk {cx},{cz} was not generated/readable: {exc}")
        seen.add(key)
        priority_scanned.append(key)
        scan_chunk(cx, cz, root)

    effective_limit = max(max_chunks, len(seen))
    for cx, cz in generated_chunks(region):
        if chunks_scanned >= effective_limit:
            break
        key = (cx, cz)
        if key in seen:
            continue
        try:
            root = BASE.read_chunk_nbt(region, cx, cz)
        except Exception:
            continue
        seen.add(key)
        scan_chunk(cx, cz, root)

    total = sum(counts.values())
    result = {
        "schema": 3,
        "deep_y": [-512, -97],
        "chunks_scanned": chunks_scanned,
        "deep_sections_scanned": deep_sections,
        "priority_chunks_requested": [[cx, cz] for cx, cz in priority_chunks],
        "priority_chunks_scanned": [[cx, cz] for cx, cz in priority_scanned],
        "chunks_with_native_ore": chunks_with_ore,
        "chunks_with_gold": chunks_with_gold,
        "chunks_with_diamond": chunks_with_diamond,
        "chunks_with_emerald": chunks_with_emerald,
        "total_deep_ore_blocks": total,
        "ore_blocks": {kind: counts.get(kind, 0) for kind in ORE_KINDS},
        "ore_block_variants": {block: block_counts.get(block, 0) for block in sorted(ORE_NAMES)},
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
    block_counts: Counter[str] = Counter()
    section = {"Y": -10, "block_states": {"palette": [{"Name": "minecraft:deepslate_iron_ore"}]}}
    if count_section(section, counts, block_counts) != 4096 or counts["iron"] != 4096:
        fail("SELF-TEST: single-palette ore counting failed")
    if block_counts["minecraft:deepslate_iron_ore"] != 4096:
        fail("SELF-TEST: exact ore block variant counting failed")

    empty = Counter()
    empty_blocks = Counter()
    section2 = {"Y": -10, "block_states": {"palette": [{"Name": "minecraft:deepslate"}]}}
    if count_section(section2, empty, empty_blocks) != 0:
        fail("SELF-TEST: host rock was counted as ore")

    if parse_chunk("31,0") != (31, 0) or parse_chunk("-17,-25") != (-17, -25):
        fail("SELF-TEST: priority chunk parser failed")
    try:
        parse_chunk("bad-chunk")
    except argparse.ArgumentTypeError:
        pass
    else:
        fail("SELF-TEST: invalid priority chunk was accepted")

    fixture = {
        "ore_blocks": {"gold": 9, "diamond": 7, "emerald": 0},
        "ore_block_variants": {
            "minecraft:deepslate_gold_ore": 9,
            "minecraft:deepslate_diamond_ore": 7,
            "minecraft:deepslate_emerald_ore": 0,
        },
    }
    missing_ores, missing_blocks = missing_required(
        fixture,
        ("gold", "diamond", "emerald"),
        (
            "minecraft:deepslate_gold_ore",
            "minecraft:deepslate_diamond_ore",
            "minecraft:deepslate_emerald_ore",
        ),
    )
    if missing_ores != ["emerald"] or missing_blocks != ["minecraft:deepslate_emerald_ore"]:
        fail("SELF-TEST: required rare-ore diagnostics failed")
    print("[NeverFolia][NeverOverworld geology audit] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit deep NR-DEV-1 NBT for native geology ore output")
    parser.add_argument("--world", type=Path)
    parser.add_argument("--max-chunks", type=int, default=256)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require", action="append", choices=ORE_KINDS, default=[], dest="required_ores")
    parser.add_argument("--require-block", action="append", choices=tuple(sorted(ORE_NAMES)), default=[], dest="required_blocks")
    parser.add_argument("--priority-chunk", action="append", type=parse_chunk, default=[], dest="priority_chunks")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.world is None:
        parser.error("--world is required")

    world = args.world.resolve()
    manifest_chunks, manifest_path = load_probe_manifest(world)
    cli_priority = tuple(dict.fromkeys(args.priority_chunks))
    priority_chunks = tuple(dict.fromkeys(cli_priority + manifest_chunks))

    required_ores_input = list(args.required_ores)
    required_blocks_input = list(args.required_blocks)
    # A smoke-generated probe manifest marks the strict CI geology profile. It
    # includes a dedicated gold probe, so gold becomes a release gate alongside
    # the explicitly requested diamond/emerald rare ores without changing generic
    # ad-hoc audits of arbitrary worlds.
    if manifest_path is not None:
        required_ores_input.insert(0, "gold")
        required_blocks_input.insert(0, "minecraft:deepslate_gold_ore")

    required_ores = tuple(dict.fromkeys(required_ores_input))
    required_blocks = tuple(dict.fromkeys(required_blocks_input))
    result = audit(world, max(1, args.max_chunks), priority_chunks)
    result["priority_chunk_source"] = str(manifest_path) if manifest_path is not None else None
    missing_ores, missing_blocks = missing_required(result, required_ores, required_blocks)
    result["required_ores"] = list(required_ores)
    result["required_blocks"] = list(required_blocks)
    result["missing_required_ores"] = missing_ores
    result["missing_required_blocks"] = missing_blocks
    result["requirements_satisfied"] = not missing_ores and not missing_blocks

    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")

    if missing_ores or missing_blocks:
        parts = []
        if missing_ores:
            parts.append("ore kinds=" + ",".join(missing_ores))
        if missing_blocks:
            parts.append("block variants=" + ",".join(missing_blocks))
        fail(
            "required native deep rare ores were not found across "
            f"{result['chunks_scanned']} generated chunks: " + "; ".join(parts)
        )


if __name__ == "__main__":
    main()
