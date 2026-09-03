#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDITOR_PATH = ROOT / "scripts/audit-never-overworld-ore-balance.py"
TUNER_PATH = ROOT / "scripts/tune-never-overworld-ore-balance-v3.py"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AUDITOR = load_module("nr_ore_balance_auditor", AUDITOR_PATH)
TUNER = load_module("nr_ore_balance_v3", TUNER_PATH)
TARGETS: dict[str, float] = dict(TUNER.TARGET_BLOCKS_PER_FULL_CHUNK)
DEFAULT_MIN_RATIO = 0.65
DEFAULT_MAX_RATIO = 1.35


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld vanilla-like ore gate] {message}")


def evaluate(actual: dict[str, float], min_ratio: float, max_ratio: float) -> dict:
    ores: dict[str, dict] = {}
    failures: list[str] = []
    for kind, target in TARGETS.items():
        value = float(actual.get(kind, 0.0))
        ratio = value / target if target > 0.0 else 0.0
        passed = min_ratio <= ratio <= max_ratio
        ores[kind] = {
            "actual_blocks_per_full_chunk": round(value, 6),
            "vanilla_26_2_target_blocks_per_full_chunk": round(target, 6),
            "ratio_to_vanilla": round(ratio, 6),
            "passed": passed,
        }
        if not passed:
            failures.append(kind)
    return {
        "schema": 1,
        "reference": "true-vanilla-26.2 / NeverOverworld-CI-Test-1 / 230 FULL chunks",
        "tolerance_ratio": [min_ratio, max_ratio],
        "emerald_policy": "excluded-from-global-density-target; biome-specific vanilla ore; presence covered by native geology audit",
        "ores": ores,
        "failed_ores": failures,
        "passed": not failures,
    }


def self_test() -> None:
    exact = evaluate(TARGETS, DEFAULT_MIN_RATIO, DEFAULT_MAX_RATIO)
    if not exact["passed"]:
        fail("SELF-TEST: exact vanilla targets did not pass")

    low = dict(TARGETS)
    low["coal"] = TARGETS["coal"] * 0.64
    result = evaluate(low, DEFAULT_MIN_RATIO, DEFAULT_MAX_RATIO)
    if result["passed"] or result["failed_ores"] != ["coal"]:
        fail("SELF-TEST: under-density coal was not rejected")

    high = dict(TARGETS)
    high["diamond"] = TARGETS["diamond"] * 1.36
    result = evaluate(high, DEFAULT_MIN_RATIO, DEFAULT_MAX_RATIO)
    if result["passed"] or result["failed_ores"] != ["diamond"]:
        fail("SELF-TEST: over-density diamond was not rejected")

    if "emerald" in TARGETS:
        fail("SELF-TEST: emerald must not use a global vanilla density target")
    print("[NeverFolia][NeverOverworld vanilla-like ore gate] SELF-TEST OK")
    print(f"  accepted ratio: {DEFAULT_MIN_RATIO:.2f}..{DEFAULT_MAX_RATIO:.2f} of measured vanilla 26.2")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gate NR-DEV-1 native deep ore blocks/FULL-chunk against measured true vanilla 26.2 density"
    )
    parser.add_argument("--world", type=Path)
    parser.add_argument("--max-chunks", type=int, default=1024)
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
    if args.max_chunks <= 0:
        parser.error("--max-chunks must be positive")
    if not (0.0 < args.min_ratio <= 1.0 <= args.max_ratio):
        parser.error("expected 0 < min-ratio <= 1 <= max-ratio")

    # same-world mode is intentional here: only the deep FULL-chunk density is
    # consumed by the gate. The upper-range counters remain useful diagnostics,
    # and its vanilla anchors are independently normalized in the NR datapack.
    audit = AUDITOR.audit(args.world.resolve(), args.max_chunks, None)
    actual = audit["deep_ore_blocks_per_full_chunk"]
    verdict = evaluate(actual, args.min_ratio, args.max_ratio)
    verdict["full_chunks_scanned"] = audit["common_full_chunks_scanned"]
    verdict["deep_y"] = audit["deep_y"]
    verdict["deep_ore_blocks"] = audit["deep_ore_blocks"]
    verdict["deep_ore_block_variants"] = audit["deep_ore_block_variants"]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(verdict, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(verdict, indent=2, ensure_ascii=False))

    if not verdict["passed"]:
        failures = ", ".join(
            f"{kind}={verdict['ores'][kind]['ratio_to_vanilla']:.3f}x"
            for kind in verdict["failed_ores"]
        )
        fail(
            f"deep ore density outside {args.min_ratio:.2f}..{args.max_ratio:.2f}x vanilla 26.2: {failures}"
        )

    print("[NeverFolia][NeverOverworld vanilla-like ore gate] PASS")


if __name__ == "__main__":
    main()
