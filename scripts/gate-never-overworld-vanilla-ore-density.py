#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDITOR_PATH = ROOT / "scripts/audit-never-overworld-ore-balance.py"
TUNER_PATH = ROOT / "scripts/tune-never-overworld-ore-balance-v3.py"
DEFAULT_VANILLA_WORLD = ROOT / "vanilla-ore-reference-test/world"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AUDITOR = load_module("nr_ore_balance_auditor", AUDITOR_PATH)
TUNER = load_module("nr_ore_balance_v3", TUNER_PATH)
CALIBRATION_TARGETS: dict[str, float] = dict(TUNER.TARGET_BLOCKS_PER_FULL_CHUNK)
DEFAULT_MIN_RATIO = 0.65
DEFAULT_MAX_RATIO = 1.35
DEFAULT_MIN_FULL_CHUNKS = 128


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld vanilla-like ore gate] {message}")


def evaluate(
    actual: dict[str, float],
    targets: dict[str, float],
    min_ratio: float,
    max_ratio: float,
) -> dict:
    ores: dict[str, dict] = {}
    failures: list[str] = []
    for kind in CALIBRATION_TARGETS:
        target = float(targets.get(kind, 0.0))
        value = float(actual.get(kind, 0.0))
        if target <= 0.0:
            failures.append(kind)
            ores[kind] = {
                "actual_blocks_per_full_chunk": round(value, 6),
                "runtime_vanilla_26_2_blocks_per_full_chunk": round(target, 6),
                "ratio_to_vanilla": None,
                "passed": False,
            }
            continue
        ratio = value / target
        passed = min_ratio <= ratio <= max_ratio
        ores[kind] = {
            "actual_blocks_per_full_chunk": round(value, 6),
            "runtime_vanilla_26_2_blocks_per_full_chunk": round(target, 6),
            "ratio_to_vanilla": round(ratio, 6),
            "passed": passed,
        }
        if not passed:
            failures.append(kind)
    return {
        "schema": 3,
        "reference": "runtime true-vanilla-26.2 world / identical seed + common FULL chunks",
        "calibration_reference": "NeverOverworld-CI-Test-1 / historical 230 FULL chunks",
        "tolerance_ratio": [min_ratio, max_ratio],
        "emerald_policy": "excluded-from-global-density-target; biome-specific vanilla ore; presence covered by native geology audit",
        "ores": ores,
        "failed_ores": failures,
        "passed": not failures,
    }


def calibration_drift(runtime_targets: dict[str, float]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for kind, historical in CALIBRATION_TARGETS.items():
        runtime = float(runtime_targets.get(kind, 0.0))
        result[kind] = None if historical <= 0.0 else round(runtime / historical, 6)
    return result


def self_test() -> None:
    exact = evaluate(CALIBRATION_TARGETS, CALIBRATION_TARGETS, DEFAULT_MIN_RATIO, DEFAULT_MAX_RATIO)
    if not exact["passed"]:
        fail("SELF-TEST: exact vanilla targets did not pass")

    low = dict(CALIBRATION_TARGETS)
    low["coal"] = CALIBRATION_TARGETS["coal"] * 0.64
    result = evaluate(low, CALIBRATION_TARGETS, DEFAULT_MIN_RATIO, DEFAULT_MAX_RATIO)
    if result["passed"] or result["failed_ores"] != ["coal"]:
        fail("SELF-TEST: under-density coal was not rejected")

    high = dict(CALIBRATION_TARGETS)
    high["diamond"] = CALIBRATION_TARGETS["diamond"] * 1.36
    result = evaluate(high, CALIBRATION_TARGETS, DEFAULT_MIN_RATIO, DEFAULT_MAX_RATIO)
    if result["passed"] or result["failed_ores"] != ["diamond"]:
        fail("SELF-TEST: over-density diamond was not rejected")

    missing = dict(CALIBRATION_TARGETS)
    missing["gold"] = 0.0
    result = evaluate(CALIBRATION_TARGETS, missing, DEFAULT_MIN_RATIO, DEFAULT_MAX_RATIO)
    if result["passed"] or "gold" not in result["failed_ores"]:
        fail("SELF-TEST: zero runtime vanilla target was not rejected")

    if "emerald" in CALIBRATION_TARGETS:
        fail("SELF-TEST: emerald must not use a global vanilla density target")
    if DEFAULT_MIN_FULL_CHUNKS < 128:
        fail("SELF-TEST: representative FULL-chunk floor drifted below 128")
    drift = calibration_drift(CALIBRATION_TARGETS)
    if any(value != 1.0 for value in drift.values() if value is not None):
        fail("SELF-TEST: calibration drift identity failed")

    print("[NeverFolia][NeverOverworld vanilla-like ore gate] RUNTIME TRUE-VANILLA SELF-TEST OK")
    print(f"  accepted ratio: {DEFAULT_MIN_RATIO:.2f}..{DEFAULT_MAX_RATIO:.2f} of runtime vanilla 26.2")
    print(f"  minimum representative sample: {DEFAULT_MIN_FULL_CHUNKS} common FULL chunks")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gate NR-DEV-1 native deep ore blocks/FULL-chunk against a runtime true-vanilla 26.2 reference"
    )
    parser.add_argument("--world", type=Path)
    parser.add_argument("--vanilla-world", type=Path)
    parser.add_argument("--max-chunks", type=int, default=1024)
    parser.add_argument("--min-full-chunks", type=int, default=DEFAULT_MIN_FULL_CHUNKS)
    parser.add_argument("--min-ratio", type=float, default=DEFAULT_MIN_RATIO)
    parser.add_argument("--max-ratio", type=float, default=DEFAULT_MAX_RATIO)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.world is None or args.output is None:
        parser.error("--world and --output are required")
    if args.max_chunks <= 0 or args.min_full_chunks <= 0:
        parser.error("--max-chunks and --min-full-chunks must be positive")
    if args.max_chunks < args.min_full_chunks:
        parser.error("--max-chunks must be >= --min-full-chunks")
    if not (0.0 < args.min_ratio <= 1.0 <= args.max_ratio):
        parser.error("expected 0 < min-ratio <= 1 <= max-ratio")

    vanilla_world = (args.vanilla_world or DEFAULT_VANILLA_WORLD).resolve()
    if not vanilla_world.is_dir():
        fail(
            f"runtime vanilla reference world not found: {vanilla_world}; "
            "generate it with smoke-test-vanilla-ore-reference.sh or pass --vanilla-world"
        )

    audit = AUDITOR.audit(args.world.resolve(), args.max_chunks, vanilla_world)
    scanned = int(audit["common_full_chunks_scanned"])
    actual = {kind: float(value) for kind, value in audit["deep_ore_blocks_per_full_chunk"].items()}
    runtime_targets = {
        kind: float(audit["vanilla_reference_ore_blocks_per_full_chunk"].get(kind, 0.0))
        for kind in CALIBRATION_TARGETS
    }
    verdict = evaluate(actual, runtime_targets, args.min_ratio, args.max_ratio)
    verdict["full_chunks_scanned"] = scanned
    verdict["minimum_required_full_chunks"] = args.min_full_chunks
    verdict["sample_size_passed"] = scanned >= args.min_full_chunks
    verdict["deep_y"] = audit["deep_y"]
    verdict["vanilla_reference_y"] = audit["vanilla_reference_y"]
    verdict["runtime_vanilla_world"] = str(vanilla_world)
    verdict["deep_ore_blocks"] = audit["deep_ore_blocks"]
    verdict["runtime_vanilla_ore_blocks"] = audit["vanilla_reference_ore_blocks"]
    verdict["deep_ore_block_variants"] = audit["deep_ore_block_variants"]
    verdict["runtime_vanilla_ore_block_variants"] = audit["vanilla_reference_ore_block_variants"]
    verdict["historical_calibration_targets"] = CALIBRATION_TARGETS
    verdict["runtime_vanilla_to_historical_calibration_ratio"] = calibration_drift(runtime_targets)
    verdict["passed"] = bool(verdict["passed"] and verdict["sample_size_passed"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verdict, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(verdict, indent=2, ensure_ascii=False))

    if not verdict["sample_size_passed"]:
        fail(f"only {scanned} common FULL chunks were available; require at least {args.min_full_chunks}")
    if verdict["failed_ores"]:
        failures = ", ".join(
            f"{kind}={verdict['ores'][kind]['ratio_to_vanilla']}x"
            for kind in verdict["failed_ores"]
        )
        fail(
            f"deep ore density outside {args.min_ratio:.2f}..{args.max_ratio:.2f}x runtime vanilla 26.2: {failures}"
        )

    print("[NeverFolia][NeverOverworld vanilla-like ore gate] PASS")


if __name__ == "__main__":
    main()
