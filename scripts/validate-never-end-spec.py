#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "worldgen-spec" / "never-end.json"


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverEnd spec] {message}")


def main() -> None:
    if not SPEC.is_file():
        fail(f"missing spec: {SPEC}")
    data = json.loads(SPEC.read_text(encoding="utf-8"))

    if data.get("schema_version") != 1:
        fail("schema_version must be 1")
    if data.get("worldgen_version") != "NE-DEV-1":
        fail("worldgen_version must be NE-DEV-1")

    dimension = data.get("dimension", {})
    expected_dimension = {
        "key": "minecraft:the_end",
        "min_y": 0,
        "height": 256,
        "max_y": 255,
    }
    for key, expected in expected_dimension.items():
        if dimension.get(key) != expected:
            fail(f"dimension.{key} must be {expected!r}, got {dimension.get(key)!r}")

    implementation = data.get("implementation", {})
    if implementation.get("custom_generator_reserved") is not True:
        fail("custom NeverEnd generator routing slot must be reserved")
    if implementation.get("custom_generator_enabled") is not False:
        fail("custom NeverEnd generator must remain disabled in TEST1")
    if implementation.get("test1_mode") != "vanilla_compatible_fallback":
        fail("TEST1 must use vanilla_compatible_fallback")
    if implementation.get("owner") != "NeverFolia":
        fail("NeverEnd owner must be NeverFolia")

    future = data.get("future_contract", {})
    for key in ("deterministic", "folia_safe", "chunk_order_independent", "custom_terrain", "custom_biomes", "custom_structures"):
        if future.get(key) is not True:
            fail(f"future_contract.{key} must be true")

    print("[NeverFolia][NeverEnd spec] NE-DEV-1 RESERVED CONTRACT OK")
    print("  TEST1: vanilla-compatible End fallback")
    print("  future: NeverEnd custom generator slot reserved")


if __name__ == "__main__":
    main()
