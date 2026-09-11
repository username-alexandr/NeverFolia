#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "scripts/hash-never-overworld-generation-chunks.py"

spec = importlib.util.spec_from_file_location("nr_r8_cavern_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise SystemExit(f"cannot import {BASE_PATH}")
BASE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BASE)
RAW = BASE.BASE

AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}
FULL = {"full", "minecraft:full"}
DEFAULT_MIN_Y = -384
DEFAULT_MAX_Y = 96
MIN_LARGE_BLOCKS = 768
MIN_BOUNDARY_CELLS = 48
MIN_VERTICAL_SPAN = 24


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld R8 dry cavern audit] {message}")


def palette_name(entry) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        value = entry.get("Name", entry.get("name"))
        if isinstance(value, str):
            return value
    raise ValueError(f"invalid palette entry: {entry!r}")


def chunk_status(root: dict) -> str:
    value = root.get("Status", root.get("status", ""))
    return value if isinstance(value, str) else ""


def section_air_mask(section: dict) -> bytearray:
    mask = bytearray(4096)
    states = section.get("block_states", section.get("BlockStates"))
    if not isinstance(states, dict):
        return mask
    raw_palette = states.get("palette")
    if not isinstance(raw_palette, list) or not raw_palette:
        return mask
    palette = [palette_name(entry) for entry in raw_palette]
    air_flags = [name in AIR for name in palette]
    if len(palette) == 1:
        if air_flags[0]:
            mask[:] = b"\x01" * 4096
        return mask
    wrapper = states.get("data")
    longs = wrapper.get("$long_array", []) if isinstance(wrapper, dict) else []
    bits = max(4, (len(palette) - 1).bit_length())
    per_long = 64 // bits
    bit_mask = (1 << bits) - 1
    for index in range(4096):
        li = index // per_long
        if li >= len(longs):
            fail(f"packed block-state data too short in section Y={section.get('Y')}")
        shift = (index % per_long) * bits
        pi = ((longs[li] & 0xFFFFFFFFFFFFFFFF) >> shift) & bit_mask
        if pi >= len(palette):
            fail(f"palette index {pi} out of range in section Y={section.get('Y')}")
        if air_flags[pi]:
            mask[index] = 1
    return mask


def chunk_air(root: dict, min_y: int, max_y: int) -> bytearray:
    layers = max_y - min_y + 1
    result = bytearray(layers * 256)
    sections = {
        int(section["Y"]): section
        for section in RAW.section_list(root)
        if isinstance(section.get("Y"), int)
    }
    min_sy = min_y // 16
    max_sy = max_y // 16
    for sy in range(min_sy, max_sy + 1):
        section = sections.get(sy)
        if section is None:
            # Missing sections in persisted FULL chunks are semantically air.
            sec_mask = bytearray(b"\x01" * 4096)
        else:
            sec_mask = section_air_mask(section)
        y0 = sy * 16
        scan_lo = max(min_y, y0)
        scan_hi = min(max_y, y0 + 15)
        for y in range(scan_lo, scan_hi + 1):
            local_y = y & 15
            source = local_y << 8
            dest = (y - min_y) << 8
            result[dest : dest + 256] = sec_mask[source : source + 256]
    return result


def generated_chunks(region: Path):
    yield from BASE.generated_chunks(region)


def component_metrics(air: bytearray, min_y: int, max_y: int) -> tuple[list[dict], int]:
    visited = bytearray(len(air))
    queue = [0] * len(air)
    components: list[dict] = []
    boundary_air = 0

    def encoded(lx: int, y: int, lz: int) -> int:
        return ((y - min_y) << 8) | (lz << 4) | lx

    def seed(lx: int, y: int, lz: int) -> None:
        nonlocal boundary_air
        start = encoded(lx, y, lz)
        if not air[start] or visited[start]:
            return
        head = 0
        tail = 1
        queue[0] = start
        visited[start] = 1
        size = 0
        boundary = 0
        ymin = y
        ymax = y
        while head < tail:
            value = queue[head]
            head += 1
            size += 1
            x = value & 15
            z = (value >> 4) & 15
            yy = min_y + (value >> 8)
            ymin = min(ymin, yy)
            ymax = max(ymax, yy)
            if x in (0, 15) or z in (0, 15):
                boundary += 1

            # Horizontal owned neighbours.
            if x > 0:
                n = value - 1
                if air[n] and not visited[n]:
                    visited[n] = 1; queue[tail] = n; tail += 1
            if x < 15:
                n = value + 1
                if air[n] and not visited[n]:
                    visited[n] = 1; queue[tail] = n; tail += 1
            if z > 0:
                n = value - 16
                if air[n] and not visited[n]:
                    visited[n] = 1; queue[tail] = n; tail += 1
            if z < 15:
                n = value + 16
                if air[n] and not visited[n]:
                    visited[n] = 1; queue[tail] = n; tail += 1
            if yy > min_y:
                n = value - 256
                if air[n] and not visited[n]:
                    visited[n] = 1; queue[tail] = n; tail += 1
            if yy < max_y:
                n = value + 256
                if air[n] and not visited[n]:
                    visited[n] = 1; queue[tail] = n; tail += 1

        boundary_air += boundary
        components.append({
            "blocks": size,
            "boundary_cells": boundary,
            "min_y": ymin,
            "max_y": ymax,
            "vertical_span": ymax - ymin + 1,
            "large_r8_candidate": (
                size >= MIN_LARGE_BLOCKS
                and boundary >= MIN_BOUNDARY_CELLS
                and (ymax - ymin + 1) >= MIN_VERTICAL_SPAN
            ),
        })

    for y in range(min_y, max_y + 1):
        for edge in range(16):
            seed(0, y, edge)
            seed(15, y, edge)
            seed(edge, y, 0)
            seed(edge, y, 15)
    return components, boundary_air


def audit(world: Path, max_chunks: int, min_y: int, max_y: int) -> dict:
    region = BASE.find_region_dir(world)
    scanned = 0
    all_components = 0
    all_blocks = 0
    boundary_cells = 0
    large_components = 0
    large_blocks = 0
    large_boundary_cells = 0
    large_spans: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    per_chunk: list[dict] = []

    for cx, cz in generated_chunks(region):
        if scanned >= max_chunks:
            break
        try:
            root = RAW.read_chunk_nbt(region, cx, cz)
        except Exception:
            continue
        status = chunk_status(root)
        status_counts[status or "<missing>"] += 1
        if status not in FULL:
            continue
        scanned += 1
        air = chunk_air(root, min_y, max_y)
        comps, boundary = component_metrics(air, min_y, max_y)
        large = [c for c in comps if c["large_r8_candidate"]]
        all_components += len(comps)
        all_blocks += sum(c["blocks"] for c in comps)
        boundary_cells += boundary
        large_components += len(large)
        large_blocks += sum(c["blocks"] for c in large)
        large_boundary_cells += sum(c["boundary_cells"] for c in large)
        for comp in large:
            span = comp["vertical_span"]
            large_spans[f"{(span // 16) * 16:03d}-{((span // 16) * 16) + 15:03d}"] += 1
        if large:
            per_chunk.append({
                "chunk": [cx, cz],
                "large_components": len(large),
                "large_blocks": sum(c["blocks"] for c in large),
                "components": large,
            })

    if scanned == 0:
        fail("no FULL chunks available")
    per_chunk.sort(key=lambda item: (-item["large_blocks"], item["chunk"]))
    return {
        "schema": 1,
        "world": str(world),
        "y_range": [min_y, max_y],
        "full_chunks_scanned": scanned,
        "status_counts": dict(sorted(status_counts.items())),
        "thresholds": {
            "min_blocks": MIN_LARGE_BLOCKS,
            "min_boundary_cells": MIN_BOUNDARY_CELLS,
            "min_vertical_span": MIN_VERTICAL_SPAN,
        },
        "boundary_connected_components": all_components,
        "boundary_connected_dry_air_blocks": all_blocks,
        "boundary_air_cells": boundary_cells,
        "large_boundary_components": large_components,
        "large_boundary_dry_air_blocks": large_blocks,
        "large_boundary_cells": large_boundary_cells,
        "large_components_per_full_chunk": round(large_components / scanned, 6),
        "large_dry_air_blocks_per_full_chunk": round(large_blocks / scanned, 6),
        "large_vertical_span_histogram": dict(sorted(large_spans.items())),
        "worst_chunks": per_chunk[:30],
    }


def self_test() -> None:
    min_y, max_y = -32, 32
    layers = max_y - min_y + 1
    air = bytearray(layers * 256)
    # Large vertical boundary corridor: must be detected when thresholds are
    # scaled conceptually, but the production thresholds intentionally reject it.
    for y in range(min_y, max_y + 1):
        for x in range(4):
            for z in range(16):
                air[((y - min_y) << 8) | (z << 4) | x] = 1
    comps, boundary = component_metrics(air, min_y, max_y)
    if len(comps) != 1 or comps[0]["blocks"] != layers * 4 * 16:
        fail(f"SELF-TEST: component BFS mismatch: {comps}")
    if boundary <= 0 or comps[0]["vertical_span"] != layers:
        fail("SELF-TEST: boundary/span metric failed")
    if not comps[0]["large_r8_candidate"]:
        fail("SELF-TEST: representative large boundary cavern was not classified")
    print("[NeverFolia][NeverOverworld R8 dry cavern audit] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path)
    parser.add_argument("--max-chunks", type=int, default=256)
    parser.add_argument("--min-y", type=int, default=DEFAULT_MIN_Y)
    parser.add_argument("--max-y", type=int, default=DEFAULT_MAX_Y)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.world is None or args.output is None:
        parser.error("--world and --output required")
    if args.max_chunks <= 0 or args.min_y > args.max_y:
        parser.error("invalid bounds")
    result = audit(args.world.resolve(), args.max_chunks, args.min_y, args.max_y)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
