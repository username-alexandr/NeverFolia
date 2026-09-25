#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path

VANILLA_MIN_Y = -64
VANILLA_MAX_Y = 319
MANIFEST = "neveroverworld-test1-manifest.json"
RESOURCE_ORE_FEATURES = (
    "ore_coal_lower",
    "ore_coal_upper",
    "ore_copper",
    "ore_copper_large",
    "ore_diamond",
    "ore_diamond_buried",
    "ore_diamond_large",
    "ore_diamond_medium",
    "ore_emerald",
    "ore_gold",
    "ore_gold_extra",
    "ore_gold_lower",
    "ore_iron_middle",
    "ore_iron_small",
    "ore_iron_upper",
    "ore_lapis",
    "ore_lapis_buried",
    "ore_redstone",
    "ore_redstone_lower",
)


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld vanilla ore anchors] {message}")


def dump_json(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def embedded_server_jar(server_jar: Path) -> zipfile.ZipFile:
    with zipfile.ZipFile(server_jar) as outer:
        candidates = [
            name
            for name in outer.namelist()
            if name.startswith("META-INF/versions/") and name.endswith("/folia-26.2.jar")
        ]
        if len(candidates) != 1:
            fail(f"expected one embedded Folia 26.2 server JAR, got {candidates}")
        payload = outer.read(candidates[0])
    return zipfile.ZipFile(io.BytesIO(payload))


def normalize_anchor(value: object) -> object:
    if not isinstance(value, dict):
        return value
    if set(value) == {"above_bottom"} and isinstance(value["above_bottom"], int):
        return {"absolute": VANILLA_MIN_Y + value["above_bottom"]}
    if set(value) == {"below_top"} and isinstance(value["below_top"], int):
        return {"absolute": VANILLA_MAX_Y - value["below_top"]}
    return {key: normalize_anchor(child) for key, child in value.items()}


def normalize_tree(value: object) -> object:
    if isinstance(value, dict):
        anchor = normalize_anchor(value)
        if anchor is not value and set(value) in ({"above_bottom"}, {"below_top"}):
            return anchor
        return {key: normalize_tree(child) for key, child in value.items()}
    if isinstance(value, list):
        return [normalize_tree(child) for child in value]
    return value


def load_feature(vanilla: zipfile.ZipFile, name: str) -> dict:
    path = f"data/minecraft/worldgen/placed_feature/{name}.json"
    try:
        value = json.loads(vanilla.read(path))
    except KeyError as exc:
        fail(f"vanilla 26.2 placed feature missing: {path}")
    if not isinstance(value, dict):
        fail(f"invalid placed feature object: {path}")
    return value


def transform(pack_payload: bytes, server_jar: Path) -> bytes:
    with embedded_server_jar(server_jar) as vanilla:
        overrides = {name: normalize_tree(load_feature(vanilla, name)) for name in RESOURCE_ORE_FEATURES}

    source = zipfile.ZipFile(io.BytesIO(pack_payload), "r")
    names = set(source.namelist())
    if MANIFEST not in names:
        fail("NeverOverworld manifest missing")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        override_paths = {f"data/minecraft/worldgen/placed_feature/{name}.json" for name in RESOURCE_ORE_FEATURES}
        for info in source.infolist():
            if info.filename in override_paths:
                continue
            raw = source.read(info.filename)
            if info.filename == MANIFEST:
                manifest = json.loads(raw)
                manifest["vanilla_resource_ore_anchor_policy"] = "resolve-original-vanilla-26.2-anchors-to-absolute"
                manifest["vanilla_resource_ore_original_bounds"] = [VANILLA_MIN_Y, VANILLA_MAX_Y]
                manifest["vanilla_resource_ore_anchor_overrides"] = list(RESOURCE_ORE_FEATURES)
                raw = dump_json(manifest)
            target.writestr(info, raw)
        for name, value in overrides.items():
            target.writestr(f"data/minecraft/worldgen/placed_feature/{name}.json", dump_json(value))
    source.close()
    return out.getvalue()


def normalize_pack(input_path: Path, server_jar: Path) -> None:
    payload = transform(input_path.read_bytes(), server_jar)
    with tempfile.NamedTemporaryFile(prefix="nr-vanilla-ore-anchors-", suffix=".zip", delete=False) as tmp:
        temp = Path(tmp.name)
        temp.write_bytes(payload)
    try:
        temp.replace(input_path)
    finally:
        temp.unlink(missing_ok=True)
    print("[NeverFolia][NeverOverworld vanilla ore anchors] ORIGINAL VANILLA ANCHORS RESTORED")
    print(f"  original bounds: Y={VANILLA_MIN_Y}..{VANILLA_MAX_Y}")
    print(f"  overridden resource ore placed features: {len(RESOURCE_ORE_FEATURES)}")


def self_test() -> None:
    if normalize_tree({"above_bottom": 0}) != {"absolute": -64}:
        fail("SELF-TEST: above_bottom=0 did not resolve to -64")
    if normalize_tree({"above_bottom": -80}) != {"absolute": -144}:
        fail("SELF-TEST: diamond lower anchor did not preserve original resolved Y")
    if normalize_tree({"above_bottom": 80}) != {"absolute": 16}:
        fail("SELF-TEST: diamond upper anchor did not preserve original resolved Y")
    if normalize_tree({"below_top": 0}) != {"absolute": 319}:
        fail("SELF-TEST: below_top=0 did not resolve to original top Y=319")
    if normalize_tree({"below_top": 8}) != {"absolute": 311}:
        fail("SELF-TEST: below_top offset resolution failed")
    fixture = {
        "placement": [
            {"type": "minecraft:height_range", "height": {"type": "minecraft:trapezoid", "min_inclusive": {"above_bottom": -32}, "max_inclusive": {"above_bottom": 32}}}
        ]
    }
    normalized = normalize_tree(fixture)
    height = normalized["placement"][0]["height"]
    if height["min_inclusive"] != {"absolute": -96} or height["max_inclusive"] != {"absolute": -32}:
        fail("SELF-TEST: nested redstone lower anchors were not normalized")
    print("[NeverFolia][NeverOverworld vanilla ore anchors] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser(description="Preserve vanilla 26.2 resource-ore vertical anchors after NeverOverworld height extension")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--server-jar", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.input is None or args.server_jar is None:
        parser.error("--input and --server-jar are required")
    if not args.input.is_file():
        fail(f"input pack not found: {args.input}")
    if not args.server_jar.is_file():
        fail(f"server JAR not found: {args.server_jar}")
    normalize_pack(args.input.resolve(), args.server_jar.resolve())


if __name__ == "__main__":
    main()
