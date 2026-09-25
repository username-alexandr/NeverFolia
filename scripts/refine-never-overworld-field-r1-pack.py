#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path

MANIFEST = "neveroverworld-test1-manifest.json"
NOISE_SETTINGS = "data/minecraft/worldgen/noise_settings/overworld.json"
TRIAL = "data/minecraft/worldgen/structure/trial_chambers.json"
STRONGHOLD_TAG = "data/minecraft/tags/worldgen/biome/has_structure/stronghold.json"

LOW_BAND_MAX = {
    "ore_coal_lower": 64,
    "ore_copper": 64,
    "ore_copper_large": 64,
    "ore_iron_small": 64,
}
HIGH_BAND_MIN = {
    "ore_iron_upper": 136,
    "ore_emerald": 136,
    "ore_gold_extra": 136,
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][field-r1 pack] {message}")


def dump(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def embedded_server(server_jar: Path) -> zipfile.ZipFile:
    with zipfile.ZipFile(server_jar) as outer:
        names = [n for n in outer.namelist() if n.startswith("META-INF/versions/") and n.endswith("/folia-26.2.jar")]
        if len(names) != 1:
            fail(f"expected one embedded Folia 26.2 JAR, got {names}")
        payload = outer.read(names[0])
    return zipfile.ZipFile(io.BytesIO(payload))


def contains_noise(value: object, noise_id: str) -> bool:
    if isinstance(value, dict):
        if value.get("type") == "minecraft:noise" and value.get("noise") == noise_id:
            return True
        return any(contains_noise(child, noise_id) for child in value.values())
    if isinstance(value, list):
        return any(contains_noise(child, noise_id) for child in value)
    return False


def gradient(from_y: int, to_y: int, from_value: float, to_value: float) -> dict:
    return {
        "type": "minecraft:y_clamped_gradient",
        "from_y": from_y,
        "to_y": to_y,
        "from_value": from_value,
        "to_value": to_value,
    }


def refine_density(value: object) -> object:
    if isinstance(value, list):
        return [refine_density(child) for child in value]
    if not isinstance(value, dict):
        return value

    node = {key: refine_density(child) for key, child in value.items()}
    if node.get("type") == "minecraft:noise":
        if node.get("noise") == "neverfolia:never_overworld/deep_chasm":
            node["xz_scale"] = 1.35
            node["y_scale"] = 0.60
        elif node.get("noise") == "neverfolia:never_overworld/deep_cavern":
            node["y_scale"] = 0.72
        return node

    if node.get("type") != "minecraft:range_choice":
        return node
    source = node.get("input")
    if contains_noise(source, "neverfolia:never_overworld/deep_cavern"):
        node["when_in_range"] = -0.72
        return node
    if contains_noise(source, "neverfolia:never_overworld/deep_tunnel"):
        node["when_in_range"] = -0.50
        return node
    if contains_noise(source, "neverfolia:never_overworld/deep_chasm"):
        node["when_in_range"] = -0.52
        # Fade vertical chasms out before the vanilla/deep blend. The original
        # y_scale=0.16 produced near-columnar voids spanning hundreds of blocks.
        return {
            "type": "minecraft:mul",
            "argument1": node,
            "argument2": gradient(-208, -128, 1.0, 0.0),
        }
    return node


def height_range(feature: dict) -> dict:
    found = [p.get("height") for p in feature.get("placement", []) if isinstance(p, dict) and p.get("type") == "minecraft:height_range"]
    if len(found) != 1 or not isinstance(found[0], dict):
        fail("resource ore feature does not contain exactly one height_range")
    return found[0]


def set_absolute_bound(feature: dict, key: str, value: int) -> None:
    height = height_range(feature)
    current = height.get(key)
    if not isinstance(current, dict) or set(current) != {"absolute"}:
        fail(f"expected normalized absolute {key}, got {current!r}")
    height[key] = {"absolute": value}


def transform(payload: bytes, server_jar: Path) -> bytes:
    source = zipfile.ZipFile(io.BytesIO(payload), "r")
    entries: dict[str, bytes] = {info.filename: source.read(info.filename) for info in source.infolist()}
    source.close()
    if MANIFEST not in entries or NOISE_SETTINGS not in entries:
        fail("NeverOverworld Core entries missing")

    noise = json.loads(entries[NOISE_SETTINGS])
    noise["noise_router"]["final_density"] = refine_density(noise["noise_router"]["final_density"])
    entries[NOISE_SETTINGS] = dump(noise)

    for name, maximum in LOW_BAND_MAX.items():
        path = f"data/minecraft/worldgen/placed_feature/{name}.json"
        feature = json.loads(entries[path])
        set_absolute_bound(feature, "max_inclusive", maximum)
        entries[path] = dump(feature)
    for name, minimum in HIGH_BAND_MIN.items():
        path = f"data/minecraft/worldgen/placed_feature/{name}.json"
        feature = json.loads(entries[path])
        set_absolute_bound(feature, "min_inclusive", minimum)
        entries[path] = dump(feature)

    with embedded_server(server_jar) as vanilla:
        trial = json.loads(vanilla.read(TRIAL))
    trial["start_height"] = {
        "type": "minecraft:uniform",
        "min_inclusive": {"absolute": -320},
        "max_inclusive": {"absolute": -96},
    }
    trial["terrain_adaptation"] = "bury"
    entries[TRIAL] = dump(trial)

    # NeverLand progression owns End access. An empty stronghold-biome tag keeps
    # the vanilla registry valid while making vanilla stronghold starts impossible.
    entries[STRONGHOLD_TAG] = dump({"replace": True, "values": []})

    manifest = json.loads(entries[MANIFEST])
    manifest["field_regression_profile"] = "field-r1"
    manifest["deep_density_profile"] = "field-r1-short-chasm-smooth-carve"
    manifest["flooded_ore_sterile_band"] = [65, 135]
    manifest["trial_chambers_range"] = [-320, -96]
    manifest["stronghold_enabled"] = False
    entries[MANIFEST] = dump(manifest)

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name in sorted(entries):
            target.writestr(name, entries[name])
    return out.getvalue()


def refine_pack(input_path: Path, server_jar: Path) -> None:
    payload = transform(input_path.read_bytes(), server_jar)
    with tempfile.NamedTemporaryFile(prefix="nr-field-r1-", suffix=".zip", delete=False) as tmp:
        temp = Path(tmp.name)
        temp.write_bytes(payload)
    try:
        temp.replace(input_path)
    finally:
        temp.unlink(missing_ok=True)
    print("[NeverFolia][field-r1 pack] FIELD REGRESSION PROFILE APPLIED")
    print("  trial chambers: Y=-320..-96")
    print("  stronghold/end portal: disabled")
    print("  flooded ore sterile band: Y=65..135")
    print("  deep chasms: shortened and faded before upper blend")


def self_test() -> None:
    sample = {
        "type": "minecraft:range_choice",
        "input": {"type": "minecraft:abs", "argument": {"type": "minecraft:noise", "noise": "neverfolia:never_overworld/deep_chasm", "xz_scale": 1.55, "y_scale": 0.16}},
        "min_inclusive": 0.0,
        "max_exclusive": 0.055,
        "when_in_range": -0.95,
        "when_out_of_range": 0.0,
    }
    refined = refine_density(sample)
    if refined.get("type") != "minecraft:mul":
        fail("SELF-TEST: chasm was not vertically windowed")
    inner = refined["argument1"]
    if inner["when_in_range"] != -0.52 or inner["input"]["argument"]["y_scale"] != 0.60:
        fail("SELF-TEST: chasm amplitude/scale not refined")
    feature = {"placement": [{"type": "minecraft:height_range", "height": {"type": "minecraft:uniform", "min_inclusive": {"absolute": 32}, "max_inclusive": {"absolute": 256}}}]}
    set_absolute_bound(feature, "min_inclusive", 136)
    if height_range(feature)["min_inclusive"] != {"absolute": 136}:
        fail("SELF-TEST: ore band rewrite failed")
    print("[NeverFolia][field-r1 pack] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--server-jar", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.input is None or args.server_jar is None:
        parser.error("--input and --server-jar are required")
    self_test()
    refine_pack(args.input.resolve(), args.server_jar.resolve())


if __name__ == "__main__":
    main()
