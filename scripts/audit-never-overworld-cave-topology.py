#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HASHER = ROOT / "scripts/hash-never-overworld-generation-chunks.py"

spec = importlib.util.spec_from_file_location("nr_topology_hasher", HASHER)
if spec is None or spec.loader is None:
    raise SystemExit(f"cannot import NeverOverworld hasher: {HASHER}")
NR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(NR)
BASE = NR.BASE

REGION_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")
DEFAULT_MIN_Y = -496
DEFAULT_MAX_Y = -96
OPEN_BLOCKS = {
    "minecraft:air",
    "minecraft:cave_air",
    "minecraft:void_air",
    "minecraft:water",
    "minecraft:lava",
    "minecraft:bubble_column",
}
FULL_STATUSES = {"full", "minecraft:full"}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld topology audit] {message}")


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
            yield rx * 32 + (index & 31), rz * 32 + (index >> 5)


def chunk_status(root: dict) -> str | None:
    raw = root.get("Status", root.get("status"))
    return raw.lower() if isinstance(raw, str) else None


def is_full_chunk(root: dict) -> bool:
    return chunk_status(root) in FULL_STATUSES


def required_section_ys(min_y: int, max_y: int) -> set[int]:
    return set(range(min_y // 16, max_y // 16 + 1))


def palette_name(entry) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        value = entry.get("Name", entry.get("name"))
        if isinstance(value, str):
            return value
    raise ValueError(f"invalid palette entry: {entry!r}")


def decode_section(section: dict) -> list[str]:
    states = section.get("block_states", section.get("BlockStates"))
    if not isinstance(states, dict):
        raise ValueError(f"section Y={section.get('Y')} has no block_states payload")
    raw_palette = states.get("palette")
    if not isinstance(raw_palette, list) or not raw_palette:
        raise ValueError(f"section Y={section.get('Y')} has no block-state palette")
    palette = [palette_name(entry) for entry in raw_palette]
    if len(palette) == 1:
        return [palette[0]] * 4096

    wrapper = states.get("data")
    longs = wrapper.get("$long_array", []) if isinstance(wrapper, dict) else []
    bits = max(4, (len(palette) - 1).bit_length())
    per_long = 64 // bits
    mask = (1 << bits) - 1
    result: list[str] = []
    for index in range(4096):
        li = index // per_long
        if li >= len(longs):
            raise ValueError(f"packed block-state data too short in section Y={section.get('Y')}")
        shift = (index % per_long) * bits
        pi = ((longs[li] & 0xFFFFFFFFFFFFFFFF) >> shift) & mask
        if pi >= len(palette):
            raise ValueError(f"palette index {pi} out of range {len(palette)}")
        result.append(palette[pi])
    return result


def decoded_sample_sections(root: dict, min_y: int, max_y: int) -> dict[int, list[str]]:
    required = required_section_ys(min_y, max_y)
    raw_sections: dict[int, dict] = {}
    for section in BASE.section_list(root):
        sy = section.get("Y")
        if isinstance(sy, int) and sy in required:
            raw_sections[sy] = section

    missing = sorted(required - set(raw_sections))
    if missing:
        raise LookupError(f"sample is missing section Y values: {missing}")

    decoded: dict[int, list[str]] = {}
    for sy in sorted(required):
        decoded[sy] = decode_section(raw_sections[sy])
    return decoded


def percentile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return float(ordered[lo])
    weight = position - lo
    return ordered[lo] * (1.0 - weight) + ordered[hi] * weight


def metrics_from_layers(layers: list[int]) -> dict:
    if not layers:
        return {
            "max_vertical_open_run": 0,
            "p95_vertical_open_run": 0.0,
            "columns_ge_128": 0,
            "columns_ge_192": 0,
            "columns_ge_256": 0,
            "max_identical_partial_mask_run": 0,
        }

    current = [0] * 256
    maximum = [0] * 256
    previous_mask: int | None = None
    repeated = 0
    max_repeated_partial = 0
    all_open = (1 << 256) - 1

    for mask in layers:
        for column in range(256):
            if (mask >> column) & 1:
                current[column] += 1
                if current[column] > maximum[column]:
                    maximum[column] = current[column]
            else:
                current[column] = 0

        if mask == previous_mask:
            repeated += 1
        else:
            previous_mask = mask
            repeated = 1
        if mask not in (0, all_open):
            max_repeated_partial = max(max_repeated_partial, repeated)

    return {
        "max_vertical_open_run": max(maximum),
        "p95_vertical_open_run": round(percentile(maximum, 0.95), 2),
        "columns_ge_128": sum(value >= 128 for value in maximum),
        "columns_ge_192": sum(value >= 192 for value in maximum),
        "columns_ge_256": sum(value >= 256 for value in maximum),
        "max_identical_partial_mask_run": max_repeated_partial,
    }


def audit_chunk(root: dict, min_y: int, max_y: int) -> dict:
    sections = decoded_sample_sections(root, min_y, max_y)

    layers: list[int] = []
    open_blocks = 0
    sampled_blocks = 0
    max_layer_open = 0
    for y in range(min_y, max_y + 1):
        sy = y // 16
        local_y = y - sy * 16
        decoded = sections[sy]
        mask = 0
        for local_z in range(16):
            for local_x in range(16):
                index = (local_y << 8) | (local_z << 4) | local_x
                if decoded[index] in OPEN_BLOCKS:
                    column = (local_z << 4) | local_x
                    mask |= 1 << column
        count = mask.bit_count()
        open_blocks += count
        sampled_blocks += 256
        max_layer_open = max(max_layer_open, count)
        layers.append(mask)

    result = metrics_from_layers(layers)
    result["open_fraction"] = round(open_blocks / sampled_blocks, 6) if sampled_blocks else 0.0
    result["max_layer_open_fraction"] = round(max_layer_open / 256.0, 6)
    return result


def audit(world: Path, max_chunks: int, min_y: int, max_y: int) -> dict:
    region = NR.find_region_dir(world)
    rows: list[dict] = []
    records_seen = 0
    skipped_not_full = 0
    skipped_incomplete_sections = 0
    skipped_decode_error = 0

    for cx, cz in generated_chunks(region):
        if len(rows) >= max_chunks:
            break
        records_seen += 1
        try:
            root = BASE.read_chunk_nbt(region, cx, cz)
        except Exception:
            skipped_decode_error += 1
            continue
        if not is_full_chunk(root):
            skipped_not_full += 1
            continue
        try:
            metrics = audit_chunk(root, min_y, max_y)
        except LookupError:
            skipped_incomplete_sections += 1
            continue
        except Exception:
            skipped_decode_error += 1
            continue
        rows.append({
            "chunk": [cx, cz],
            "status": chunk_status(root),
            **metrics,
        })

    if not rows:
        fail(
            "no complete FULL NeverOverworld chunks were available for the requested vertical sample; "
            f"records_seen={records_seen} not_full={skipped_not_full} "
            f"incomplete_sections={skipped_incomplete_sections} decode_errors={skipped_decode_error}"
        )

    longest = sorted(rows, key=lambda row: (row["max_vertical_open_run"], row["max_identical_partial_mask_run"]), reverse=True)
    boxiest = sorted(rows, key=lambda row: (row["max_identical_partial_mask_run"], row["max_vertical_open_run"]), reverse=True)
    return {
        "schema": 2,
        "purpose": "diagnose giant vertical canyons and axis-aligned extruded cave boxes in complete FULL chunks only",
        "sample_y": [min_y, max_y],
        "required_section_y": [min(required_section_ys(min_y, max_y)), max(required_section_ys(min_y, max_y))],
        "open_blocks": sorted(OPEN_BLOCKS),
        "selection": {
            "full_statuses": sorted(FULL_STATUSES),
            "records_seen": records_seen,
            "chunks_scanned": len(rows),
            "skipped_not_full": skipped_not_full,
            "skipped_incomplete_sections": skipped_incomplete_sections,
            "skipped_decode_error": skipped_decode_error,
        },
        "chunks_scanned": len(rows),
        "global": {
            "max_vertical_open_run": max(row["max_vertical_open_run"] for row in rows),
            "max_identical_partial_mask_run": max(row["max_identical_partial_mask_run"] for row in rows),
            "chunks_with_columns_ge_192": sum(row["columns_ge_192"] > 0 for row in rows),
            "chunks_with_columns_ge_256": sum(row["columns_ge_256"] > 0 for row in rows),
            "mean_open_fraction": round(sum(row["open_fraction"] for row in rows) / len(rows), 6),
        },
        "top_vertical_open_chunks": longest[:20],
        "top_repeated_mask_chunks": boxiest[:20],
    }


def self_test() -> None:
    # A 200-block vertical shaft in one local column must be detected exactly.
    layers = []
    for y in range(240):
        layers.append(1 if 20 <= y < 220 else 0)
    metrics = metrics_from_layers(layers)
    if metrics["max_vertical_open_run"] != 200 or metrics["columns_ge_192"] != 1:
        fail(f"SELF-TEST vertical run failed: {metrics}")

    # A partial 16x16 mask repeated for 40 Y layers models an axis-aligned
    # extrusion/box and must be surfaced by the repeated-mask diagnostic.
    partial = (1 << 128) - 1
    metrics = metrics_from_layers([partial] * 40)
    if metrics["max_identical_partial_mask_run"] != 40:
        fail(f"SELF-TEST repeated-mask run failed: {metrics}")

    section = {"Y": -10, "block_states": {"palette": [{"Name": "minecraft:air"}]}}
    if decode_section(section) != ["minecraft:air"] * 4096:
        fail("SELF-TEST single-palette decode failed")

    if not is_full_chunk({"Status": "minecraft:full"}) or not is_full_chunk({"status": "full"}):
        fail("SELF-TEST FULL chunk status normalization failed")
    if is_full_chunk({"Status": "minecraft:noise"}) or is_full_chunk({}):
        fail("SELF-TEST non-FULL chunk status rejection failed")

    expected_sections = {-31, -30, -29, -28, -27, -26, -25, -24, -23, -22, -21, -20, -19, -18, -17, -16, -15, -14, -13, -12, -11, -10, -9, -8, -7, -6}
    if required_section_ys(DEFAULT_MIN_Y, DEFAULT_MAX_Y) != expected_sections:
        fail("SELF-TEST requested section coverage calculation failed")

    try:
        decode_section({"Y": -10})
    except ValueError:
        pass
    else:
        fail("SELF-TEST missing block_states must not be interpreted as air")

    print("[NeverFolia][NeverOverworld topology audit] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit NeverOverworld cave topology for giant vertical chasms and box-like extrusion")
    parser.add_argument("--world", type=Path)
    parser.add_argument("--max-chunks", type=int, default=256)
    parser.add_argument("--min-y", type=int, default=DEFAULT_MIN_Y)
    parser.add_argument("--max-y", type=int, default=DEFAULT_MAX_Y)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fail-vertical-run-above", type=int)
    parser.add_argument("--fail-identical-mask-run-above", type=int)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.world is None:
        parser.error("--world is required")
    if args.min_y > args.max_y:
        parser.error("--min-y must not exceed --max-y")

    result = audit(args.world.resolve(), max(1, args.max_chunks), args.min_y, args.max_y)
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")

    global_metrics = result["global"]
    if args.fail_vertical_run_above is not None and global_metrics["max_vertical_open_run"] > args.fail_vertical_run_above:
        fail(
            f"vertical open run {global_metrics['max_vertical_open_run']} exceeds gate "
            f"{args.fail_vertical_run_above}"
        )
    if args.fail_identical_mask_run_above is not None and global_metrics["max_identical_partial_mask_run"] > args.fail_identical_mask_run_above:
        fail(
            f"repeated partial layer mask run {global_metrics['max_identical_partial_mask_run']} exceeds gate "
            f"{args.fail_identical_mask_run_above}"
        )


if __name__ == "__main__":
    main()
