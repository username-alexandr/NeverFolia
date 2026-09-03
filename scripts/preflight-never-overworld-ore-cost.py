#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GEOMETRY_PATH = ROOT / "scripts/preflight-never-overworld-native-ore-geometry.py"
MAX_AVG_CANDIDATE_CELLS = 400.0
MAX_P95_CANDIDATE_CELLS = 500
MAX_AVG_INTERSECTING_VEINS = 20.0
MAX_P95_INTERSECTING_VEINS = 26
MAX_AVG_BBOX_VOXEL_TESTS = 25000.0
MAX_P95_BBOX_VOXEL_TESTS = 40000


def load_geometry():
    spec = importlib.util.spec_from_file_location("nr_ore_geometry_preflight", GEOMETRY_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import {GEOMETRY_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = load_geometry()


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld ore cost preflight] {message}")


def cost_kind(seed: int, chunk_x: int, chunk_z: int, kind) -> tuple[int, int, int]:
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

    candidates = 0
    intersecting = 0
    bbox_voxel_tests = 0

    for cell_y in range(min_cell_y, max_cell_y + 1):
        for cell_z in range(min_cell_z, max_cell_z + 1):
            for cell_x in range(min_cell_x, max_cell_x + 1):
                candidates += 1
                h = P.hash_cell(seed, kind.salt, cell_x, cell_y, cell_z)
                gate = P.unit(h)
                h = P.mix64(h)
                center_x = cell_x * float(kind.cell_size) + P.unit(h) * kind.cell_size
                h = P.mix64(h)
                center_y = cell_y * float(kind.cell_size) + P.unit(h) * kind.cell_size
                if center_y < kind.min_y or center_y > kind.max_y:
                    continue
                h = P.mix64(h)
                center_z = cell_z * float(kind.cell_size) + P.unit(h) * kind.cell_size

                province = P.province_strength(
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

                h = P.mix64(h)
                yaw = P.unit(h) * P.TAU
                h = P.mix64(h)
                pitch = (P.unit(h) - 0.5) * kind.pitch_span
                h = P.mix64(h)
                length = P.lerp(kind.min_length, kind.max_length, P.unit(h))
                h = P.mix64(h)
                radius = P.lerp(kind.min_radius, kind.max_radius, P.unit(h))

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

                intersecting += 1
                bbox_voxel_tests += (
                    (max_x - min_x + 1)
                    * (max_y - min_y + 1)
                    * (max_z - min_z + 1)
                )

    return candidates, intersecting, bbox_voxel_tests


def p95(values: list[int]) -> int:
    ordered = sorted(values)
    return ordered[math.ceil(0.95 * len(ordered)) - 1]


def evaluate() -> dict:
    cfgs = P.configs()
    coords = P.sample_coords(P.SAMPLE_CHUNKS)
    candidate_totals: list[int] = []
    intersecting_totals: list[int] = []
    bbox_totals: list[int] = []

    for chunk_x, chunk_z in coords:
        candidates = 0
        intersecting = 0
        bbox = 0
        for kind_name in P.KINDS:
            c, i, b = cost_kind(P.TEST_SEED, chunk_x, chunk_z, cfgs[kind_name])
            candidates += c
            intersecting += i
            bbox += b
        candidate_totals.append(candidates)
        intersecting_totals.append(intersecting)
        bbox_totals.append(bbox)

    metrics = {
        "candidate_cells": {
            "average": round(sum(candidate_totals) / len(candidate_totals), 6),
            "p95": p95(candidate_totals),
            "max": max(candidate_totals),
        },
        "intersecting_veins": {
            "average": round(sum(intersecting_totals) / len(intersecting_totals), 6),
            "p95": p95(intersecting_totals),
            "max": max(intersecting_totals),
        },
        "bbox_voxel_tests": {
            "average": round(sum(bbox_totals) / len(bbox_totals), 6),
            "p95": p95(bbox_totals),
            "max": max(bbox_totals),
        },
    }

    failures: list[str] = []
    if metrics["candidate_cells"]["average"] > MAX_AVG_CANDIDATE_CELLS:
        failures.append("candidate_cells_average")
    if metrics["candidate_cells"]["p95"] > MAX_P95_CANDIDATE_CELLS:
        failures.append("candidate_cells_p95")
    if metrics["intersecting_veins"]["average"] > MAX_AVG_INTERSECTING_VEINS:
        failures.append("intersecting_veins_average")
    if metrics["intersecting_veins"]["p95"] > MAX_P95_INTERSECTING_VEINS:
        failures.append("intersecting_veins_p95")
    if metrics["bbox_voxel_tests"]["average"] > MAX_AVG_BBOX_VOXEL_TESTS:
        failures.append("bbox_voxel_tests_average")
    if metrics["bbox_voxel_tests"]["p95"] > MAX_P95_BBOX_VOXEL_TESTS:
        failures.append("bbox_voxel_tests_p95")

    return {
        "schema": 1,
        "purpose": "cheap CPU-cost guard for deterministic NR native ore generation",
        "sample_chunks": P.SAMPLE_CHUNKS,
        "limits": {
            "max_average_candidate_cells": MAX_AVG_CANDIDATE_CELLS,
            "max_p95_candidate_cells": MAX_P95_CANDIDATE_CELLS,
            "max_average_intersecting_veins": MAX_AVG_INTERSECTING_VEINS,
            "max_p95_intersecting_veins": MAX_P95_INTERSECTING_VEINS,
            "max_average_bbox_voxel_tests": MAX_AVG_BBOX_VOXEL_TESTS,
            "max_p95_bbox_voxel_tests": MAX_P95_BBOX_VOXEL_TESTS,
        },
        "metrics": metrics,
        "failures": failures,
        "passed": not failures,
    }


def self_test() -> None:
    verdict = evaluate()
    if not verdict["passed"]:
        fail(f"SELF-TEST: current v3 exceeds geometry CPU budget: {verdict['failures']}")
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    print("[NeverFolia][NeverOverworld ore cost preflight] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight NR native ore geometry CPU cost")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    verdict = evaluate()
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(verdict, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    if not verdict["passed"]:
        fail(f"geometry CPU budget exceeded: {verdict['failures']}")
    print("[NeverFolia][NeverOverworld ore cost preflight] PASS")


if __name__ == "__main__":
    main()
