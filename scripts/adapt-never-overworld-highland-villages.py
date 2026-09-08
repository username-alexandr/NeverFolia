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
VILLAGE_MAX_GENERATED_BBOX_SPAN = 256
VILLAGE_MAX_GENERATED_BBOX_AREA = 65536

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
#
# Runtime safety is no longer inferred from a fixed radius. The cheap prefilter
# checks only the candidate centre above the flood plane. Structure#generate then
# builds the deterministic Jigsaw layout and the actual StructureStart bounding
# box is checked column-by-column before the start is persisted. Fast locate uses
# the same read-only generated layout preview. Persisted NBT bbox water=0 remains
# the independent final arbiter.
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
    for stale in (
        "village_bbox_overhang_margin",
        "village_dry_samples",
        "village_dry_radius",
        "village_dry_step",
    ):
        manifest.pop(stale, None)
    manifest["village_surface_policy"] = "generated-jigsaw-bbox-all-columns-dry-highland"
    manifest["village_prefilter"] = "candidate-center-world-surface-wg-gte129"
    manifest["village_layout_safety"] = "structure-start-bbox-all-xz-world-surface-wg-gte129"
    manifest["village_fast_locate_layout"] = "same-structure-generate-preview-references0"
    manifest["village_jigsaw_max_distance_from_center"] = VILLAGE_JIGSAW_REACH
    manifest["village_generated_bbox_max_span"] = VILLAGE_MAX_GENERATED_BBOX_SPAN
    manifest["village_generated_bbox_max_area"] = VILLAGE_MAX_GENERATED_BBOX_AREA
    manifest["village_persisted_bbox_gate"] = "all-blocks-zero-water-y128"
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
    print("[NeverFolia][NeverOverworld highland villages] GENERATED-BBOX HIGHLAND POLICY METADATA APPLIED")
    print("  prefilter: candidate centre WORLD_SURFACE_WG >= 129")
    print("  final runtime safety: actual generated StructureStart bbox, every X/Z column")
    print("  fast locate: same Structure#generate preview with references=0")
    print("  vanilla village Jigsaw max_distance_from_center: 80 (reference only)")
    print("  accepted generated bbox limit: 256x256 / 65536 columns")
    print("  plains fallback: savanna plateau / windswept savanna / stony peaks")
    print("  savanna fallback: savanna plateau / windswept savanna / stony peaks")
    print("  taiga fallback: grove / snowy slopes")
    print("  cold peaks are not added to plains/savanna")
    print("  persisted village bbox all-block Y=128 water=0 audit remains authoritative")
    print("  structure spacing: vanilla 34")


def self_test() -> None:
    if VILLAGE_JIGSAW_REACH != 80:
        fail("SELF-TEST: vanilla Jigsaw reach reference drifted")
    if VILLAGE_MAX_GENERATED_BBOX_SPAN != 256 or VILLAGE_MAX_GENERATED_BBOX_AREA != 65536:
        fail("SELF-TEST: generated bbox safety cap drifted")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(MANIFEST, dump({
            "schema": 1,
            "village_bbox_overhang_margin": 16,
            "village_dry_samples": 169,
            "village_dry_radius": 96,
            "village_dry_step": 16,
        }))
    result = transform(buf.getvalue())
    with zipfile.ZipFile(io.BytesIO(result)) as z:
        manifest = json.loads(z.read(MANIFEST))
        for name, values in EXTRA.items():
            tag = json.loads(z.read(f"data/minecraft/tags/worldgen/biome/has_structure/{name}.json"))
            if tag != {"replace": False, "values": values}:
                fail(f"SELF-TEST: wrong biome tag for {name}: {tag}")
    if manifest.get("village_surface_policy") != "generated-jigsaw-bbox-all-columns-dry-highland":
        fail("SELF-TEST: generated-bbox policy marker missing")
    expected = {
        "village_prefilter": "candidate-center-world-surface-wg-gte129",
        "village_layout_safety": "structure-start-bbox-all-xz-world-surface-wg-gte129",
        "village_fast_locate_layout": "same-structure-generate-preview-references0",
        "village_jigsaw_max_distance_from_center": 80,
        "village_generated_bbox_max_span": 256,
        "village_generated_bbox_max_area": 65536,
        "village_persisted_bbox_gate": "all-blocks-zero-water-y128",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            fail(f"SELF-TEST: {key} mismatch: {manifest.get(key)} != {value}")
    for stale in ("village_bbox_overhang_margin", "village_dry_samples", "village_dry_radius", "village_dry_step"):
        if stale in manifest:
            fail(f"SELF-TEST: stale reach96 manifest key survived: {stale}")
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
