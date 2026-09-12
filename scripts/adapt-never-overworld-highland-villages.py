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
VILLAGE_PREDICTION_REACH = 64
VILLAGE_PREDICTION_STEP = 32
VILLAGE_PREDICTION_SAMPLES = 25

# R9 V7 keeps village locate and generation on the same zero-generation
# preliminary-surface envelope. Runtime diagnostics on the deterministic TEST1
# seed showed that reach64 restores plains/savanna availability without the
# Structure.generate watchdog path, while desert/snowy/taiga still exhaust on
# biome filtering. Add only variant-appropriate highland biomes actually seen on
# dry rejected candidates; do not broaden into generic forest/jungle/caves.
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
    ):
        manifest.pop(stale, None)

    manifest["village_surface_policy"] = "r9-v7-shared-preliminary-envelope-highland"
    manifest["village_prefilter"] = "center-gte129-biome-then-5x5-preliminary-envelope"
    manifest["village_generation_policy"] = "same-5x5-preliminary-envelope-as-fast-locate"
    manifest["village_fast_locate_layout"] = "zero-generation-shared-5x5-preliminary-envelope"
    manifest["village_prediction_reach"] = VILLAGE_PREDICTION_REACH
    manifest["village_prediction_step"] = VILLAGE_PREDICTION_STEP
    manifest["village_prediction_samples"] = VILLAGE_PREDICTION_SAMPLES
    manifest["village_jigsaw_max_distance_from_center"] = VILLAGE_JIGSAW_REACH
    manifest["village_persisted_bbox_gate"] = "all-blocks-zero-water-y128"
    manifest["village_spacing"] = 34
    manifest["village_highland_biomes"] = EXTRA
    manifest["village_highland_fallbacks"] = FALLBACKS
    manifest["village_fallback_basis"] = "R9 V6 dry-candidate biome-key diagnostics"
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
    print("[NeverFolia][NeverOverworld highland villages] R9 V7 SHARED-ENVELOPE HIGHLAND POLICY APPLIED")
    print("  locate/generation envelope: 5x5 reach64 step32, zero Structure.generate preview")
    print("  desert fallback: stony peaks / savanna plateau")
    print("  snowy fallback: jagged peaks / frozen peaks")
    print("  taiga fallback: grove / snowy slopes / jagged / frozen / stony peaks")
    print("  plains/savanna keep non-snowy fallbacks")
    print("  persisted actual Jigsaw bbox water=0 remains authoritative final safety gate")
    print("  structure spacing: vanilla 34")


def self_test() -> None:
    if VILLAGE_JIGSAW_REACH != 80:
        fail("SELF-TEST: vanilla Jigsaw reach reference drifted")
    if (VILLAGE_PREDICTION_REACH, VILLAGE_PREDICTION_STEP, VILLAGE_PREDICTION_SAMPLES) != (64, 32, 25):
        fail("SELF-TEST: R9 V7 reach64 prediction contract drifted")

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
        }))
    result = transform(buf.getvalue())
    with zipfile.ZipFile(io.BytesIO(result)) as z:
        manifest = json.loads(z.read(MANIFEST))
        for name, values in EXTRA.items():
            tag = json.loads(z.read(f"data/minecraft/tags/worldgen/biome/has_structure/{name}.json"))
            if tag != {"replace": False, "values": values}:
                fail(f"SELF-TEST: wrong biome tag for {name}: {tag}")

    expected = {
        "village_surface_policy": "r9-v7-shared-preliminary-envelope-highland",
        "village_fast_locate_layout": "zero-generation-shared-5x5-preliminary-envelope",
        "village_prediction_reach": 64,
        "village_prediction_step": 32,
        "village_prediction_samples": 25,
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
    ):
        if stale in manifest:
            fail(f"SELF-TEST: stale generated-bbox/reach96 key survived: {stale}")

    if FALLBACKS["village_desert"] != ["minecraft:stony_peaks", "minecraft:savanna_plateau"]:
        fail("SELF-TEST: desert V6-backed fallback contract missing")
    if FALLBACKS["village_snowy"] != ["minecraft:jagged_peaks", "minecraft:frozen_peaks"]:
        fail("SELF-TEST: snowy V6-backed fallback contract missing")
    if "minecraft:jagged_peaks" not in FALLBACKS["village_taiga"] or "minecraft:frozen_peaks" not in FALLBACKS["village_taiga"]:
        fail("SELF-TEST: taiga V6-backed cold peak fallback missing")

    cold = {"minecraft:jagged_peaks", "minecraft:frozen_peaks", "minecraft:snowy_slopes"}
    for variant in ("village_plains", "village_savanna", "village_desert"):
        if cold.intersection(EXTRA[variant]):
            fail(f"SELF-TEST: snowy peak fallback leaked into warm/non-snowy {variant}")

    print("[NeverFolia][NeverOverworld highland villages] SELF-TEST OK")
    print("  R9 V7 fallback set is V6-diagnostic-backed and metadata matches reach64 runtime")


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
