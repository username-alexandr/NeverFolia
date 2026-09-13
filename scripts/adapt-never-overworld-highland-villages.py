#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path

MANIFEST = "neveroverworld-test1-manifest.json"
VILLAGE_JIGSAW_REACH = 80  # vanilla reference only
VILLAGE_LOCATE_RINGS = 128
VILLAGE_STRICT_PROBES = 12
FLOOD_LEVEL = 128

# R9 V17 keeps /locate and generation on the same zero-generation strict
# preliminary-surface contract. The highland biome expansion below is the exact
# V6/V7 diagnostic-backed set used by the successful V17 isolated runtime proof.
# Actual shoreline safety is no longer guessed from this biome list: once the
# real StructureStart exists during FEATURES, V17 reclaims the actual enclosing
# village bbox in the owning chunk, and persisted full-bbox water=0 remains the
# independent release gate.
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
        "minecraft:jagged_peaks",
        "minecraft:frozen_peaks",
        "minecraft:stony_peaks",
    ],
    "village_snowy": [
        "minecraft:grove",
        "minecraft:snowy_slopes",
        "minecraft:jagged_peaks",
        "minecraft:frozen_peaks",
    ],
    "village_savanna": [
        "minecraft:savanna_plateau",
        "minecraft:windswept_savanna",
        "minecraft:stony_peaks",
    ],
    "village_desert": [
        "minecraft:badlands",
        "minecraft:wooded_badlands",
        "minecraft:eroded_badlands",
        "minecraft:stony_peaks",
        "minecraft:savanna_plateau",
    ],
}

FALLBACKS = {
    "village_plains": [
        "minecraft:savanna_plateau",
        "minecraft:windswept_savanna",
        "minecraft:stony_peaks",
    ],
    "village_savanna": ["minecraft:stony_peaks"],
    "village_desert": ["minecraft:stony_peaks", "minecraft:savanna_plateau"],
    "village_snowy": ["minecraft:jagged_peaks", "minecraft:frozen_peaks"],
    "village_taiga": [
        "minecraft:grove",
        "minecraft:snowy_slopes",
        "minecraft:jagged_peaks",
        "minecraft:frozen_peaks",
        "minecraft:stony_peaks",
    ],
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
        "village_generated_bbox_max_span",
        "village_generated_bbox_max_area",
        "village_prediction_reach",
        "village_prediction_step",
        "village_prediction_samples",
        "village_layout_safety",
    ):
        manifest.pop(stale, None)

    manifest["village_surface_policy"] = "r9-v17-strict12-rings128-actual-bbox-reclamation"
    manifest["village_prefilter"] = "center-gte129-biome-then-strict12-preliminary-probes"
    manifest["village_generation_policy"] = "same-strict12-preliminary-probes-as-fast-locate"
    manifest["village_fast_locate_layout"] = "zero-generation-strict12-preliminary-rings128"
    manifest["village_strict_probe_count"] = VILLAGE_STRICT_PROBES
    manifest["village_locate_max_candidate_rings"] = VILLAGE_LOCATE_RINGS
    manifest["village_jigsaw_max_distance_from_center"] = VILLAGE_JIGSAW_REACH
    manifest["village_actual_bbox_reclamation"] = "features-owning-chunk-y80-128-waterline-foundation"
    manifest["village_reclamation_flood_level"] = FLOOD_LEVEL
    manifest["village_persisted_bbox_gate"] = "all-blocks-zero-water-y128"
    manifest["village_spacing"] = 34
    manifest["village_highland_biomes"] = EXTRA
    manifest["village_highland_fallbacks"] = FALLBACKS
    manifest["village_fallback_basis"] = "R9 V6 dry-candidate biome-key diagnostics; carried into proven V17"
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
    print("[NeverFolia][NeverOverworld highland villages] R9 V17 PRODUCTION HIGHLAND POLICY APPLIED")
    print("  locate: strict 12/12 preliminary probes, hardcoded rings128")
    print("  generation: same strict 12/12 preliminary probes")
    print("  desert fallback: stony peaks / savanna plateau")
    print("  snowy fallback: jagged peaks / frozen peaks")
    print("  taiga fallback: grove / snowy slopes / jagged / frozen / stony peaks")
    print("  actual generated bbox: owning-chunk reclamation before LIGHT flood")
    print("  persisted full Jigsaw bbox Y=128 water=0 remains authoritative")
    print("  structure spacing: vanilla 34")


def self_test() -> None:
    if VILLAGE_JIGSAW_REACH != 80:
        fail("SELF-TEST: vanilla Jigsaw reach reference drifted")
    if VILLAGE_LOCATE_RINGS != 128 or VILLAGE_STRICT_PROBES != 12 or FLOOD_LEVEL != 128:
        fail("SELF-TEST: V17 production constants drifted")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(MANIFEST, dump({
            "schema": 1,
            "village_bbox_overhang_margin": 16,
            "village_dry_samples": 169,
            "village_dry_radius": 96,
            "village_dry_step": 16,
            "village_generated_bbox_max_span": 256,
            "village_generated_bbox_max_area": 65536,
            "village_prediction_reach": 64,
            "village_prediction_step": 32,
            "village_prediction_samples": 25,
            "village_layout_safety": "old-generated-bbox-scan",
        }))
    result = transform(buf.getvalue())
    with zipfile.ZipFile(io.BytesIO(result)) as z:
        manifest = json.loads(z.read(MANIFEST))
        for name, values in EXTRA.items():
            tag = json.loads(z.read(f"data/minecraft/tags/worldgen/biome/has_structure/{name}.json"))
            if tag != {"replace": False, "values": values}:
                fail(f"SELF-TEST: wrong biome tag for {name}: {tag}")

    expected = {
        "village_surface_policy": "r9-v17-strict12-rings128-actual-bbox-reclamation",
        "village_fast_locate_layout": "zero-generation-strict12-preliminary-rings128",
        "village_generation_policy": "same-strict12-preliminary-probes-as-fast-locate",
        "village_strict_probe_count": 12,
        "village_locate_max_candidate_rings": 128,
        "village_actual_bbox_reclamation": "features-owning-chunk-y80-128-waterline-foundation",
        "village_reclamation_flood_level": 128,
        "village_persisted_bbox_gate": "all-blocks-zero-water-y128",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            fail(f"SELF-TEST: {key} mismatch: {manifest.get(key)} != {value}")

    for stale in (
        "village_bbox_overhang_margin",
        "village_dry_samples",
        "village_dry_radius",
        "village_dry_step",
        "village_generated_bbox_max_span",
        "village_generated_bbox_max_area",
        "village_prediction_reach",
        "village_prediction_step",
        "village_prediction_samples",
        "village_layout_safety",
    ):
        if stale in manifest:
            fail(f"SELF-TEST: stale pre-V17 manifest key survived: {stale}")

    required_taiga = {"minecraft:jagged_peaks", "minecraft:frozen_peaks", "minecraft:stony_peaks"}
    if not required_taiga.issubset(EXTRA["village_taiga"]):
        fail("SELF-TEST: proven taiga highland fallback set missing")
    if FALLBACKS["village_desert"] != ["minecraft:stony_peaks", "minecraft:savanna_plateau"]:
        fail("SELF-TEST: desert diagnostic-backed fallback contract missing")
    if FALLBACKS["village_snowy"] != ["minecraft:jagged_peaks", "minecraft:frozen_peaks"]:
        fail("SELF-TEST: snowy diagnostic-backed fallback contract missing")

    cold = {"minecraft:jagged_peaks", "minecraft:frozen_peaks", "minecraft:snowy_slopes"}
    for variant in ("village_plains", "village_savanna", "village_desert"):
        if cold.intersection(EXTRA[variant]):
            fail(f"SELF-TEST: snowy peak fallback leaked into warm/non-snowy {variant}")

    print("[NeverFolia][NeverOverworld highland villages] R9 V17 PRODUCTION SELF-TEST OK")
    print("  proven V6/V7 biome set retained; manifest describes final V17 policy")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.input is None:
        parser.error("--input is required")
    self_test()
    apply_pack(args.input.resolve())


if __name__ == "__main__":
    main()
