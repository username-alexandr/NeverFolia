#!/usr/bin/env python3
from __future__ import annotations

import argparse
import io
import json
import tempfile
import zipfile
from pathlib import Path

MANIFEST = "neveroverworld-test1-manifest.json"

# NeverOverworld leaves only high terrain above the Y=128 flood plane. Runtime
# matrix QA proved that meadow/cherry and old-growth taiga families do not offer
# reliable strict dry village starts on the deterministic TEST1 seed. Persisted
# NBT biome QA on the dense radius32 candidate additionally proved that dry
# plains/savanna placement candidates are dominated by mountain biomes. Keep
# climate-specific natural families, and add only the warm/non-snowy mountain
# fallback that was actually observed on dry candidates:
#   plains  -> elevated savanna grasslands + stony peaks
#   savanna -> savanna highlands + stony peaks
#   taiga   -> cold grove / snowy slopes
# Do not add jagged/frozen peaks or snowy slopes to plains/savanna: that would
# make the architectural variant cross into visibly incompatible cold terrain.
# R6 splits village variants into independent structure sets with distinct salts,
# so these biome overlaps do not steal weighted slots from another variant.
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
    manifest["village_surface_policy"] = "dense-dry-highland-radius32-stony-fallback"
    manifest["village_dry_samples"] = 25
    manifest["village_dry_radius"] = 32
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
    print("[NeverFolia][NeverOverworld highland villages] DENSE RADIUS32 HIGHLAND POLICY APPLIED")
    print("  final dry safety: dense 5x5 / 25 samples, radius=32 in runtime policy")
    print("  plains fallback: savanna plateau / windswept savanna / stony peaks")
    print("  savanna fallback: savanna plateau / windswept savanna / stony peaks")
    print("  taiga fallback: grove / snowy slopes")
    print("  cold peaks are not added to plains/savanna")
    print("  persisted village bbox zero-water audit remains authoritative")
    print("  structure spacing: vanilla 34")


def self_test() -> None:
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
    if manifest.get("village_surface_policy") != "dense-dry-highland-radius32-stony-fallback":
        fail("SELF-TEST: manifest marker missing")
    if manifest.get("village_dry_samples") != 25 or manifest.get("village_dry_radius") != 32:
        fail(f"SELF-TEST: dense radius32 dry contract mismatch: {manifest}")
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
