#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TUNER_PATH = ROOT / "scripts/tune-never-overworld-ore-balance-v3.py"
MASK64 = (1 << 64) - 1
TAU = math.pi * 2.0
PROVINCE_SCALE = 384
DEEP_MAX_Y = -96
TEST_SEED = 0x4E525F44454E5331
COORD_STATE = 0x4E525F47454F4D31
SAMPLE_CHUNKS = 128
MIN_AVG_RATIO = 0.75
MAX_AVG_RATIO = 1.45
MAX_BARREN_FRACTION = 0.65
MAX_P95_RATIO = 6.25
KINDS = ("coal", "iron", "copper", "gold", "redstone", "lapis", "diamond")


def load_tuner():
    spec = importlib.util.spec_from_file_location("nr_ore_balance_v3", TUNER_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import {TUNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TUNER = load_tuner()
TARGETS: dict[str, float] = dict(TUNER.TARGET_BLOCKS_PER_FULL_CHUNK)


@dataclass(frozen=True)
class OreConfig:
    salt: int
    cell_size: int
    base_chance: float
    min_province: float
    min_y: int
    max_y: int
    min_length: float
    max_length: float
    min_radius: float
    max_radius: float
    pitch_span: float
    fill: float


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld geometry preflight] {message}")


def parse_number(token: str) -> float:
    token = token.strip()
    if token.endswith(("D", "d")):
        token = token[:-1]
    return float(token)


def parse_int(token: str) -> int:
    token = token.strip()
    if token == "DEEP_MAX_Y":
        return DEEP_MAX_Y
    return int(token)


def parse_salt(token: str) -> int:
    token = token.strip()
    if token.endswith(("L", "l")):
        token = token[:-1]
    return int(token, 0) & MASK64


def parse_entry(entry: str) -> tuple[str, OreConfig]:
    match = re.match(r"\s*(\w+)\((.*)\)(?:,|;)\s*$", entry)
    if match is None:
        fail(f"could not parse v3 ore entry: {entry!r}")
    kind = match.group(1).lower()
    parts = [part.strip() for part in match.group(2).split(",")]
    if len(parts) < 12:
        fail(f"v3 ore entry has too few fields for {kind}: {len(parts)}")
    return kind, OreConfig(
        salt=parse_salt(parts[0]),
        cell_size=int(parts[1]),
        base_chance=parse_number(parts[2]),
        min_province=parse_number(parts[3]),
        min_y=parse_int(parts[4]),
        max_y=parse_int(parts[5]),
        min_length=parse_number(parts[6]),
        max_length=parse_number(parts[7]),
        min_radius=parse_number(parts[8]),
        max_radius=parse_number(parts[9]),
        pitch_span=parse_number(parts[10]),
        fill=parse_number(parts[11]),
    )


def configs() -> dict[str, OreConfig]:
    result: dict[str, OreConfig] = {}
    for key, entry in TUNER.NEW.items():
        kind, config = parse_entry(entry)
        if kind != key.lower():
            fail(f"v3 key/entry mismatch: {key} vs {kind}")
        if kind in KINDS:
            result[kind] = config
    missing = [kind for kind in KINDS if kind not in result]
    if missing:
        fail(f"missing v3 geometry configs: {missing}")
    return result


def mix64(value: int) -> int:
    value &= MASK64
    value ^= value >> 30
    value = (value * 0xBF58476D1CE4E5B9) & MASK64
    value ^= value >> 27
    value = (value * 0x94D049BB133111EB) & MASK64
    value ^= value >> 31
    return value & MASK64


def hash_cell(seed: int, salt: int, x: int, y: int, z: int) -> int:
    value = (seed ^ salt) & MASK64
    value ^= (x * 0x9E3779B97F4A7C15) & MASK64
    value = mix64(value)
    value ^= (y * 0xC2B2AE3D27D4EB4F) & MASK64
    value = mix64(value)
    value ^= (z * 0x165667B19E3779F9) & MASK64
    return mix64(value)


def hash_block(seed: int, salt: int, x: int, y: int, z: int) -> int:
    return hash_cell(seed ^ 0x94D049BB133111EB, salt, x, y, z)


def unit(value: int) -> float:
    return ((value & MASK64) >> 11) * (2.0 ** -53)


def smooth(value: float) -> float:
    return value * value * (3.0 - 2.0 * value)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def province_strength(seed: int, x: float, z: float, salt: int) -> float:
    gx = math.floor(x / PROVINCE_SCALE)
    gz = math.floor(z / PROVINCE_SCALE)
    fx = smooth(x / PROVINCE_SCALE - gx)
    fz = smooth(z / PROVINCE_SCALE - gz)
    v00 = unit(hash_cell(seed, salt, gx, 0, gz))
    v10 = unit(hash_cell(seed, salt, gx + 1, 0, gz))
    v01 = unit(hash_cell(seed, salt, gx, 0, gz + 1))
    v11 = unit(hash_cell(seed, salt, gx + 1, 0, gz + 1))
    return lerp(lerp(v00, v10, fx), lerp(v01, v11, fx), fz)


def sample_coords(count: int) -> list[tuple[int, int]]:
    state = COORD_STATE
    result: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    while len(result) < count:
        state = mix64(state + 0x9E3779B97F4A7C15)
        cx = int((state & 0x1FF) - 256)
        state = mix64(state + 0x9E3779B97F4A7C15)
        cz = int((state & 0x1FF) - 256)
        coord = (cx, cz)
        if coord not in seen:
            seen.add(coord)
            result.append(coord)
    return result


def intended_voxels(seed: int, chunk_x: int, chunk_z: int, kind: OreConfig) -> int:
    chunk_min_x = chunk_x * 16
    chunk_max_x = chunk_min_x + 15
    chunk_min_z = chunk_z * 16
    chunk_max_z = chunk_min_z + 15
    reach = math.ceil(kind.max_length * 0.5 + kind.max_radius + 3.0)

    min_cell_x = math.floor((chunk_min_x - reach) / kind.cell_size)
    max_cell_x = math.floor((chunk_max_x + reach) / kind.cell_size)
    min_cell_z = math.floor((chunk_min_z - reach) / kind.cell_size)
    max_cell_z = math.floor((chunk_max_z + reach) / kind.cell_size)
    min_cell_y = math.floor((kind.min_y - reach) / kind.cell_size)
    max_cell_y = math.floor((kind.max_y + reach) / kind.cell_size)

    voxels: set[tuple[int, int, int]] = set()
    for cell_y in range(min_cell_y, max_cell_y + 1):
        for cell_z in range(min_cell_z, max_cell_z + 1):
            for cell_x in range(min_cell_x, max_cell_x + 1):
                h = hash_cell(seed, kind.salt, cell_x, cell_y, cell_z)
                gate = unit(h)
                h = mix64(h)
                center_x = cell_x * float(kind.cell_size) + unit(h) * kind.cell_size
                h = mix64(h)
                center_y = cell_y * float(kind.cell_size) + unit(h) * kind.cell_size
                if center_y < kind.min_y or center_y > kind.max_y:
                    continue
                h = mix64(h)
                center_z = cell_z * float(kind.cell_size) + unit(h) * kind.cell_size

                province = province_strength(
                    seed,
                    center_x,
                    center_z,
                    kind.salt ^ 0x6A09E667F3BCC909,
                )
                if province < kind.min_province:
                    continue
                chance = kind.base_chance * (0.55 + province * 0.75)
                if gate >= min(0.98, chance):
                    continue

                h = mix64(h)
                yaw = unit(h) * TAU
                h = mix64(h)
                pitch = (unit(h) - 0.5) * kind.pitch_span
                h = mix64(h)
                length = lerp(kind.min_length, kind.max_length, unit(h))
                h = mix64(h)
                radius = lerp(kind.min_radius, kind.max_radius, unit(h))

                horizontal = math.cos(pitch)
                dx = math.cos(yaw) * horizontal
                dy = math.sin(pitch)
                dz = math.sin(yaw) * horizontal
                half = length * 0.5
                ax = center_x - dx * half
                ay = center_y - dy * half
                az = center_z - dz * half
                bx = center_x + dx * half
                by = center_y + dy * half
                bz = center_z + dz * half

                min_x = max(chunk_min_x, math.floor(min(ax, bx) - radius - 1.0))
                max_x = min(chunk_max_x, math.floor(max(ax, bx) + radius + 1.0))
                min_z = max(chunk_min_z, math.floor(min(az, bz) - radius - 1.0))
                max_z = min(chunk_max_z, math.floor(max(az, bz) + radius + 1.0))
                min_y = max(kind.min_y, math.floor(min(ay, by) - radius - 1.0))
                max_y = min(kind.max_y, math.floor(max(ay, by) + radius + 1.0))
                if min_x > max_x or min_y > max_y or min_z > max_z:
                    continue

                vx = bx - ax
                vy = by - ay
                vz = bz - az
                segment_length_squared = vx * vx + vy * vy + vz * vz

                for y in range(min_y, max_y + 1):
                    for z in range(min_z, max_z + 1):
                        for x in range(min_x, max_x + 1):
                            px = x + 0.5
                            py = y + 0.5
                            pz = z + 0.5
                            t = (
                                (px - ax) * vx
                                + (py - ay) * vy
                                + (pz - az) * vz
                            ) / segment_length_squared
                            t = max(0.0, min(1.0, t))
                            qx = ax + vx * t
                            qy = ay + vy * t
                            qz = az + vz * t
                            ddx = px - qx
                            ddy = py - qy
                            ddz = pz - qz
                            taper = 0.58 + 0.42 * math.sin(math.pi * t)
                            roughness = 0.82 + 0.36 * unit(
                                hash_block(seed, kind.salt, x, y, z)
                            )
                            local_radius = radius * taper * roughness
                            if (
                                ddx * ddx + ddy * ddy + ddz * ddz
                                > local_radius * local_radius
                            ):
                                continue
                            if (
                                unit(
                                    hash_block(
                                        seed ^ 0xD1B54A32D192ED03,
                                        kind.salt,
                                        x,
                                        y,
                                        z,
                                    )
                                )
                                > kind.fill
                            ):
                                continue
                            voxels.add((x, y, z))
    return len(voxels)


def percentile95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def evaluate() -> dict:
    cfgs = configs()
    coords = sample_coords(SAMPLE_CHUNKS)
    ores: dict[str, dict] = {}
    failures: list[str] = []

    for kind in KINDS:
        target = float(TARGETS[kind])
        values = [intended_voxels(TEST_SEED, cx, cz, cfgs[kind]) for cx, cz in coords]
        average = sum(values) / len(values)
        average_ratio = average / target
        barren_fraction = sum(value == 0 for value in values) / len(values)
        p95 = percentile95(values)
        p95_ratio = p95 / target
        passed = (
            MIN_AVG_RATIO <= average_ratio <= MAX_AVG_RATIO
            and barren_fraction <= MAX_BARREN_FRACTION
            and p95_ratio <= MAX_P95_RATIO
        )
        ores[kind] = {
            "average_intended_voxels_per_chunk": round(average, 6),
            "vanilla_reference_blocks_per_full_chunk": round(target, 6),
            "average_ratio_to_vanilla": round(average_ratio, 6),
            "barren_chunk_fraction": round(barren_fraction, 6),
            "p95_intended_voxels": p95,
            "p95_ratio_to_vanilla_average": round(p95_ratio, 6),
            "max_intended_voxels": max(values),
            "passed": passed,
        }
        if not passed:
            failures.append(kind)

    return {
        "schema": 1,
        "purpose": "cheap deterministic native-geometry preflight before Java/runtime gates",
        "sample_chunks": SAMPLE_CHUNKS,
        "synthetic_seed": f"0x{TEST_SEED:016x}",
        "limits": {
            "average_ratio_to_vanilla": [MIN_AVG_RATIO, MAX_AVG_RATIO],
            "max_barren_chunk_fraction": MAX_BARREN_FRACTION,
            "max_p95_ratio_to_vanilla_average": MAX_P95_RATIO,
        },
        "ores": ores,
        "failed_ores": failures,
        "passed": not failures,
    }


def self_test() -> None:
    if mix64(0x123456789ABCDEF0) != 0x9629F58E8EC5B906:
        fail("SELF-TEST: mix64 drifted from Java helper semantics")
    if sample_coords(5) != [(52, -159), (-39, -171), (-114, -236), (159, 94), (-121, 141)]:
        fail("SELF-TEST: deterministic chunk sample changed")
    if set(TARGETS) != set(KINDS):
        fail(f"SELF-TEST: expected targets {KINDS}, got {sorted(TARGETS)}")
    verdict = evaluate()
    if not verdict["passed"]:
        fail(f"SELF-TEST: current v3 geometry failed preflight: {verdict['failed_ores']}")
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    print("[NeverFolia][NeverOverworld geometry preflight] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cheap deterministic preflight for NR-DEV-1 native ore geometry"
    )
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    verdict = evaluate()
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(verdict, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    if not verdict["passed"]:
        fail(f"geometry preflight failed: {verdict['failed_ores']}")
    print("[NeverFolia][NeverOverworld geometry preflight] PASS")


if __name__ == "__main__":
    main()
