#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path

MANIFEST = "neveroverworld-test1-manifest.json"
VILLAGE_JIGSAW_REACH = 80
VILLAGE_BBOX_MARGIN = 16
VILLAGE_DRY_REACH = VILLAGE_JIGSAW_REACH + VILLAGE_BBOX_MARGIN
VILLAGE_DRY_STEP = 16
VILLAGE_DRY_AXIS_SAMPLES = (VILLAGE_DRY_REACH * 2) // VILLAGE_DRY_STEP + 1
VILLAGE_DRY_SAMPLES = VILLAGE_DRY_AXIS_SAMPLES * VILLAGE_DRY_AXIS_SAMPLES

# NeverOverworld leaves only high terrain above the Y=128 flood plane. Runtime
# matrix QA proved that meadow/cherry and old-growth taiga families do not offer
# reliable strict dry village starts on the deterministic TEST1 seed. Persisted
# NBT biome QA additionally proved that dry plains/savanna placement candidates
# are dominated by mountain biomes. Keep climate-specific natural families and
# add only the warm/non-snowy mountain fallback actually observed on candidates:
#   plains  -> elevated savanna grasslands + stony peaks
#   savanna -> savanna highlands + stony peaks
#   taiga   -> cold grove / snowy slopes
# Do not add jagged/frozen peaks or snowy slopes to plains/savanna: that would
# make the architectural variant cross into visibly incompatible cold terrain.
# R6 splits village variants into independent structure sets with distinct salts,
# so these biome overlaps do not steal weighted slots from another variant.
# Runtime safety is now sized from vanilla 26.2 Jigsaw max_distance_from_center
# (80) plus one 16-block bbox-overhang margin: reach96, step16, 13x13/169 probes.
EXTRA = {
    "village_plains": [
        "minecraft:meadow",
        "minecraft:cherry_grove",
        "minecraft:savanna_plateau",
        "minecraft:windswept_savanna",
        "minecraft:stony_peaks",
    ],
    "village_taiga": [
        "minecraft:old_growth_pine_taiga",
        "minecraft:old_growth_spruce_taiga",
        "minecraft:grove",
        "minecraft:snowy_slopes",
    ],
    "village_snowy": ["minecraft:grove", "minecraft:snowy_slopes"],
    "village_savanna": [
        "minecraft:savanna_plateau",
        "minecraft:windswept_savanna",
        "minecraft:stony_peaks",
    ],
    "village_desert": ["minecraft:badlands", "minecraft:wooded_badlands", "minecraft:eroded_badlands"],
}


def fail(message: str) -> None:
    raise SystemExit(f"[NeverFolia][NeverOverworld highland villages] {message}")


def dump(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def transform(payload: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(payload), "r") as source:
        entries = {info.filename: source.read(info.filename) for info in source.infolist()}
    if MANIFEST not in entries:
        fail("NeverOverworld manifest missing")
    for name, values in EXTRA.items():
        path = f"data/minecraft/tags/worldgen/biome/has_structure/{name}.json"
        if path in entries:
            fail(f"pack already overrides {path}; merge policy must be reviewed")
        entries[path] = dump({"replace": False, "values": values})
    manifest = json.loads(entries[MANIFEST])
    manifest["village_surface_policy"] = "bbox-sized-dry-highland-reach96-step16-stony-fallback"
    manifest["village_jigsaw_max_distance_from_center"] = VILLAGE_JIGSAW_REACH
    manifest["village_bbox_overhang_margin"] = VILLAGE_BBOX_MARGIN
    manifest["village_dry_samples"] = VILLAGE_DRY_SAMPLES
    manifest["village_dry_radius"] = VILLAGE_DRY_REACH
    manifest["village_dry_step"] = VILLAGE_DRY_STEP
    manifest["village_spacing"] = 34
    manifest["village_highland_biomes"] = EXTRA
    manifest["village_highland_fallbacks"] = {
        "village_plains": [
            "minecraft:savanna_plateau",
            "minecraft:windswept_savanna",
            "minecraft:stony_peaks",
        ],
        "village_savanna": ["minecraft:stony_peaks"],
        "village_taiga": ["minecraft:grove", "minecraft:snowy_slopes"],
    }
    entries[MANIFEST] = dump(manifest)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as target:
        for name in sorted(entries):
            target.writestr(name, entries[name])
    return out.getvalue()


def apply_pack(path: Path) -> None:
    payload = transform(path.read_bytes())
    with tempfile.NamedTemporaryFile(prefix="nr-highland-villages-", suffix=".zip", delete=False) as tmp:
        temp = Path(tmp.name)
        temp.write_bytes(payload)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
    print("[NeverFolia][NeverOverworld highland villages] REACH96 HIGHLAND POLICY METADATA APPLIED")
    print("  final dry safety: 13x13 / 169 samples, reach=96, step=16 in runtime policy")
    print("  geometry basis: vanilla Jigsaw reach=80 + bbox margin=16")
    print("  plains fallback: savanna plateau / windswept savanna / stony peaks")
    print("  savanna fallback: savanna plateau / windswept savanna / stony peaks")
    print("  taiga fallback: grove / snowy slopes")
    print("  cold peaks are not added to plains/savanna")
    print("  persisted village bbox zero-water audit remains authoritative")
    print("  structure spacing: vanilla 34")


def self_test() -> None:
    if VILLAGE_DRY_REACH != 96 or VILLAGE_DRY_STEP != 16 or VILLAGE_DRY_SAMPLES != 169:
        fail("SELF-TEST: reach96 geometry constants drifted")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(MANIFEST, dump({"schema": 1}))
    result = transform(buf.getvalue())
    with zipfile.ZipFile(io.BytesIO(result)) as z:
        manifest = json.loads(z.read(MANIFEST))
        for name, values in EXTRA.items():
            tag = json.loads(z.read(f"data/minecraft/tags/worldgen/biome/has_structure/{name}.json"))
            if tag != {"replace": False, "values": values}:
                fail(f"SELF-TEST: wrong biome tag for {name}: {tag}")
    if manifest.get("village_surface_policy") != "bbox-sized-dry-highland-reach96-step16-stony-fallback":
        fail("SELF-TEST: manifest marker missing")
    expected_geometry = {
        "village_jigsaw_max_distance_from_center": 80,
        "village_bbox_overhang_margin": 16,
        "village_dry_samples": 169,
        "village_dry_radius": 96,
        "village_dry_step": 16,
    }
    for key, expected in expected_geometry.items():
        if manifest.get(key) != expected:
            fail(f"SELF-TEST: {key} mismatch: {manifest.get(key)} != {expected}")
    fallbacks = manifest.get("village_highland_fallbacks", {})
    if fallbacks.get("village_plains") != [
        "minecraft:savanna_plateau", "minecraft:windswept_savanna", "minecraft:stony_peaks"
    ]:
        fail("SELF-TEST: plains stony-peaks fallback contract missing")
    if fallbacks.get("village_savanna") != ["minecraft:stony_peaks"]:
        fail("SELF-TEST: savanna stony-peaks fallback contract missing")
    if fallbacks.get("village_taiga") != ["minecraft:grove", "minecraft:snowy_slopes"]:
        fail("SELF-TEST: taiga fallback contract missing")
    for variant in ("village_plains", "village_savanna"):
        cold = {"minecraft:jagged_peaks", "minecraft:frozen_peaks", "minecraft:snowy_slopes"}
        if cold.intersection(EXTRA[variant]):
            fail(f"SELF-TEST: cold mountain biome leaked into {variant}")
    print("[NeverFolia][NeverOverworld highland villages] SELF-TEST OK")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(); return
    if args.input is None:
        parser.error("--input is required")
    self_test()
    apply_pack(args.input.resolve())


if __name__ == "__main__":
    main()
