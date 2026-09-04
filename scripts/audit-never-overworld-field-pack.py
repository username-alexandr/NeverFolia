#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path

MANIFEST = "neveroverworld-test1-manifest.json"
TRIAL = "data/minecraft/worldgen/structure/trial_chambers.json"
STRONGHOLD = "data/minecraft/tags/worldgen/biome/has_structure/stronghold.json"

LOW_MAX = {
    "ore_coal_lower": 64,
    "ore_copper": 64,
    "ore_copper_large": 64,
    "ore_iron_small": 64,
}
HIGH_MIN = {
    "ore_iron_upper": 136,
    "ore_emerald": 136,
    "ore_gold_extra": 136,
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld field pack audit] {message}")


def load_json(zf: zipfile.ZipFile, path: str) -> dict:
    try:
        return json.loads(zf.read(path))
    except KeyError:
        fail(f"missing datapack entry: {path}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path}: {exc}")


def absolute_bound(feature: dict, key: str) -> int:
    heights = [
        p.get("height") for p in feature.get("placement", [])
        if isinstance(p, dict) and p.get("type") == "minecraft:height_range"
    ]
    if len(heights) != 1 or not isinstance(heights[0], dict):
        fail("placed feature does not contain exactly one minecraft:height_range")
    raw = heights[0].get(key)
    if not isinstance(raw, dict) or set(raw) != {"absolute"} or not isinstance(raw.get("absolute"), int):
        fail(f"expected absolute {key}, got {raw!r}")
    return raw["absolute"]


def audit_bytes(payload: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        manifest = load_json(zf, MANIFEST)
        if manifest.get("field_regression_profile") != "field-r1":
            fail(f"field_regression_profile drifted: {manifest.get('field_regression_profile')!r}")
        if manifest.get("flooded_ore_sterile_band") != [65, 135]:
            fail(f"flooded ore sterile band drifted: {manifest.get('flooded_ore_sterile_band')!r}")
        if manifest.get("stronghold_enabled") is not False:
            fail("manifest must explicitly disable stronghold")

        stronghold = load_json(zf, STRONGHOLD)
        if stronghold != {"replace": True, "values": []}:
            fail(f"stronghold biome tag is not empty/replace=true: {stronghold!r}")

        trial = load_json(zf, TRIAL)
        height = trial.get("start_height")
        expected_trial = {
            "type": "minecraft:uniform",
            "min_inclusive": {"absolute": -320},
            "max_inclusive": {"absolute": -96},
        }
        if height != expected_trial:
            fail(f"trial chamber range drifted: {height!r}")
        if trial.get("terrain_adaptation") != "bury":
            fail(f"trial chamber terrain_adaptation drifted: {trial.get('terrain_adaptation')!r}")

        ore_bounds: dict[str, dict[str, int]] = {}
        for name, maximum in LOW_MAX.items():
            path = f"data/minecraft/worldgen/placed_feature/{name}.json"
            feature = load_json(zf, path)
            actual = absolute_bound(feature, "max_inclusive")
            if actual != maximum:
                fail(f"{name} max_inclusive={actual}, expected {maximum}")
            ore_bounds[name] = {"max_inclusive": actual}
        for name, minimum in HIGH_MIN.items():
            path = f"data/minecraft/worldgen/placed_feature/{name}.json"
            feature = load_json(zf, path)
            actual = absolute_bound(feature, "min_inclusive")
            if actual != minimum:
                fail(f"{name} min_inclusive={actual}, expected {minimum}")
            ore_bounds[name] = {"min_inclusive": actual}

    return {
        "schema": 1,
        "field_regression_profile": "field-r1",
        "stronghold_enabled": False,
        "trial_chambers_y": [-320, -96],
        "flooded_ore_sterile_band": [65, 135],
        "ore_bounds": ore_bounds,
    }


def feature(minimum: int, maximum: int) -> dict:
    return {
        "placement": [{
            "type": "minecraft:height_range",
            "height": {
                "type": "minecraft:uniform",
                "min_inclusive": {"absolute": minimum},
                "max_inclusive": {"absolute": maximum},
            },
        }]
    }


def fixture() -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr(MANIFEST, json.dumps({
            "field_regression_profile": "field-r1",
            "flooded_ore_sterile_band": [65, 135],
            "stronghold_enabled": False,
        }))
        zf.writestr(STRONGHOLD, json.dumps({"replace": True, "values": []}))
        zf.writestr(TRIAL, json.dumps({
            "start_height": {
                "type": "minecraft:uniform",
                "min_inclusive": {"absolute": -320},
                "max_inclusive": {"absolute": -96},
            },
            "terrain_adaptation": "bury",
        }))
        for name in LOW_MAX:
            zf.writestr(f"data/minecraft/worldgen/placed_feature/{name}.json", json.dumps(feature(-64, 64)))
        for name in HIGH_MIN:
            zf.writestr(f"data/minecraft/worldgen/placed_feature/{name}.json", json.dumps(feature(136, 319)))
    return out.getvalue()


def self_test() -> None:
    result = audit_bytes(fixture())
    if result["trial_chambers_y"] != [-320, -96] or result["stronghold_enabled"] is not False:
        fail(f"SELF-TEST unexpected result: {result}")
    print("[NeverFolia][NeverOverworld field pack audit] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit immutable TEST1 field-r1 datapack regressions")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.input is None:
        parser.error("--input is required")
    result = audit_bytes(args.input.resolve().read_bytes())
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
